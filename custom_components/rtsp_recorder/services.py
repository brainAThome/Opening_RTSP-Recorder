"""Service handlers for RTSP Recorder.

This module contains all HA service handlers, extracted from __init__.py
to improve maintainability (HIGH-001 Fix from Audit Report v1.0.7).

Services:
- save_recording: Record a stream (manual or motion-triggered)
- analyze_recording: Analyze a single recording
- analyze_all_recordings: Batch analyze multiple recordings
- delete_recording: Delete a single recording and its thumbnail
- delete_all_recordings: Bulk delete with optional filters
"""
import os
import re
import glob
import asyncio
import datetime
from datetime import timedelta
from typing import Any, Callable

from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .helpers import (
    log_to_file,
    _validate_media_path,
    _list_video_files,
    _get_analysis_semaphore,
)
from .recorder import async_record_stream, async_take_snapshot
from .analysis import analyze_recording
from .people_db import _load_people_db
from .analysis_helpers import _build_analysis_index


def register_services(
    hass,
    entry,
    config_data: dict,
    storage_path: str,
    snapshot_path_base: str,
    analysis_output_path: str,
    analysis_detector_url: str,
    analysis_frame_interval: int,
    analysis_objects: list[str],
    analysis_device: str,
    analysis_enabled: bool,
    analysis_auto_new: bool,
    analysis_detector_confidence: float,
    analysis_face_enabled: bool,
    analysis_face_confidence: float,
    analysis_face_match_threshold: float,
    analysis_face_store_embeddings: bool,
    people_db_path: str,
    person_entities_enabled: bool,
    get_sensor_snapshot_func: Callable,
    resolve_auto_device_func: Callable,
    update_person_entities_func: Callable,
    update_person_entities_for_video_func: Callable,
):
    """Register all RTSP Recorder services.
    
    Args:
        hass: Home Assistant instance
        entry: Config entry
        config_data: Merged config data
        storage_path: Path to recordings storage
        snapshot_path_base: Path to snapshots
        analysis_output_path: Path for analysis results
        analysis_detector_url: Detector service URL
        analysis_frame_interval: Frame interval for analysis
        analysis_objects: Objects to detect
        analysis_device: Default analysis device
        analysis_enabled: Whether analysis is enabled
        analysis_auto_new: Auto-analyze new recordings
        analysis_detector_confidence: Detection confidence
        analysis_face_enabled: Face detection enabled
        analysis_face_confidence: Face detection confidence
        analysis_face_match_threshold: Face match threshold
        analysis_face_store_embeddings: Store face embeddings
        people_db_path: People database path
        person_entities_enabled: Person entities enabled
        get_sensor_snapshot_func: Function to get sensor snapshot
        resolve_auto_device_func: Function to resolve auto device
        update_person_entities_func: Function to update person entities from result
        update_person_entities_for_video_func: Function to update person entities for video
    """

    async def _wait_for_file_ready(path: str, max_wait_s: int = 120, stable_checks: int = 3, interval_s: int = 3) -> bool:
        """Wait until a file exists and its size is stable."""
        checks = 0
        last_size = -1
        waited = 0
        while waited <= max_wait_s:
            exists = await hass.async_add_executor_job(os.path.exists, path)
            if exists:
                try:
                    size = await hass.async_add_executor_job(os.path.getsize, path)
                except Exception:
                    size = -1
                if size > 0 and size == last_size:
                    checks += 1
                else:
                    checks = 0
                last_size = size
                if checks >= stable_checks:
                    return True
            await asyncio.sleep(interval_s)
            waited += interval_s
        return False

    def _extract_camera_name_from_path(video_path: str) -> str:
        """Extract camera name from video path like /media/rtsp_recordings/CameraName/file.mp4"""
        parts = video_path.replace("\\", "/").split("/")
        for i, part in enumerate(parts):
            if part in ("rtsp_recordings", "recordings") and i + 1 < len(parts) - 1:
                return parts[i + 1]
        if len(parts) >= 2:
            return parts[-2]
        return ""

    async def handle_save_recording(call: ServiceCall = None, camera_name: str = None, duration: int = 30, snapshot_delay: float = 0):
        """Handle recording. Can be called via Service (manual) or Internal Event (auto)."""
        try:
            entity_id = None
            clean_name_raw = None
            
            # Case A: Service Call
            if call:
                log_to_file("Service save_recording called!")
                entity_id = call.data.get("entity_id")
                if not entity_id:
                    log_to_file("ERROR: No entity_id provided")
                    return
                
                state = hass.states.get(entity_id)
                if not state:
                    log_to_file(f"ERROR: Entity {entity_id} not found")
                    return
                friendly_name = state.attributes.get("friendly_name", entity_id)
                
                clean_name_raw = re.sub(r"[^\w\s-]", "", friendly_name).strip().replace(" ", "_")
                clean_name = clean_name_raw
                
                duration = call.data.get("duration", duration)
                snapshot_delay = call.data.get("snapshot_delay", snapshot_delay)

            # Case B: Internal Call
            elif camera_name:
                log_to_file(f"Internal Motion Trigger for: {camera_name}")
                clean_name_raw = camera_name
                clean_name = clean_name_raw
                found_entity = None
                for state in hass.states.async_all("camera"):
                    fn = re.sub(r"[^\w\s-]", "", state.attributes.get("friendly_name", "")).strip().replace(" ", "_")
                    if fn == clean_name or clean_name in state.entity_id:
                        found_entity = state.entity_id
                        break
                if found_entity:
                    entity_id = found_entity

            else:
                return

            for char in [":", "/", "\\", "?", "*", "\"", "<", ">", "|"]:
                clean_name = clean_name.replace(char, "")

            if not clean_name:
                clean_name = "unknown"

            rtsp_key = f"rtsp_url_{clean_name}"
            legacy_rtsp_key = f"rtsp_url_{clean_name_raw}" if clean_name_raw else None
            rtsp_url = config_data.get(rtsp_key, "")
            if not rtsp_url and legacy_rtsp_key and legacy_rtsp_key != rtsp_key:
                rtsp_url = config_data.get(legacy_rtsp_key, "")
            use_rtsp = isinstance(rtsp_url, str) and rtsp_url.strip()
            if use_rtsp:
                rtsp_url = rtsp_url.strip()

            if not entity_id and not use_rtsp:
                log_to_file(f"ERROR: Could not find Camera Entity or RTSP URL for {clean_name}")
                return

            # 1. Video Recording
            cam_folder = os.path.join(storage_path, clean_name)
            if not os.path.exists(cam_folder):
                os.makedirs(cam_folder, exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            full_path = os.path.join(cam_folder, f"{clean_name}_{timestamp}.mp4")
            
            log_to_file(f"Recording to: {full_path}")

            if use_rtsp:
                await async_record_stream(hass, rtsp_url, duration, full_path)
            else:
                await hass.services.async_call("camera", "record", {
                    "entity_id": entity_id,
                    "filename": full_path,
                    "duration": duration,
                    "lookback": 0
                })
            
            # 2. Snapshot
            snap_folder = os.path.join(snapshot_path_base, clean_name)
            if not os.path.exists(snap_folder):
                os.makedirs(snap_folder, exist_ok=True)
                
            snap_filename = f"{clean_name}_{timestamp}.jpg"
            snap_full_path = os.path.join(snap_folder, snap_filename)
            
            if use_rtsp:
                log_to_file(f"Taking snapshot to: {snap_full_path}")
                await async_take_snapshot(hass, rtsp_url, snap_full_path, delay=snapshot_delay)
            else:
                if snapshot_delay > 0:
                    log_to_file(f"Waiting {snapshot_delay}s before snapshot...")
                    await asyncio.sleep(snapshot_delay)

                log_to_file(f"Taking snapshot to: {snap_full_path}")
                
                await hass.services.async_call("camera", "snapshot", {
                    "entity_id": entity_id,
                    "filename": snap_full_path
                })

            # 3. Auto-Analyze after recording
            if analysis_enabled and analysis_auto_new:
                async def _auto_analyze_when_ready(path: str, cam_name: str, rec_duration: int):
                    try:
                        await asyncio.sleep(rec_duration + 2)

                        ready = await _wait_for_file_ready(path, max_wait_s=120, stable_checks=3, interval_s=3)
                        if not ready:
                            log_to_file(f"Recording not ready for auto-analysis (timeout): {path}")
                            return

                        log_to_file(f"Auto-analyzing new recording: {path}")
                        perf_snapshot = get_sensor_snapshot_func()

                        cam_objects_key = f"analysis_objects_{cam_name}"
                        cam_specific_objects = config_data.get(cam_objects_key, [])
                        objects_to_use = cam_specific_objects if cam_specific_objects else analysis_objects

                        cam_detector_conf = config_data.get(f"detector_confidence_{cam_name}", 0)
                        cam_face_conf = config_data.get(f"face_confidence_{cam_name}", 0)
                        cam_face_threshold = config_data.get(f"face_match_threshold_{cam_name}", 0)
                        
                        detector_conf_to_use = cam_detector_conf if cam_detector_conf > 0 else analysis_detector_confidence
                        face_conf_to_use = cam_face_conf if cam_face_conf > 0 else analysis_face_confidence
                        face_threshold_to_use = cam_face_threshold if cam_face_threshold > 0 else analysis_face_match_threshold

                        people_data = await _load_people_db(people_db_path)
                        people = people_data.get("people", [])
                        auto_device = await resolve_auto_device_func()
                        result = await analyze_recording(
                            video_path=path,
                            output_root=analysis_output_path,
                            objects=objects_to_use,
                            device=auto_device,
                            interval_s=analysis_frame_interval,
                            perf_snapshot=perf_snapshot,
                            detector_url=analysis_detector_url,
                            detector_confidence=detector_conf_to_use,
                            face_enabled=analysis_face_enabled,
                            face_confidence=face_conf_to_use,
                            face_match_threshold=face_threshold_to_use,
                            face_store_embeddings=analysis_face_store_embeddings,
                            people_db=people,
                            face_detector_url=analysis_detector_url,
                        )
                        if person_entities_enabled:
                            try:
                                updated = update_person_entities_func(result or {})
                                if not updated:
                                    update_person_entities_for_video_func(path)
                            except Exception:
                                pass
                        log_to_file(f"Auto-analysis completed for: {path}")
                    except Exception as ae:
                        log_to_file(f"Auto-analysis error: {ae}")

                hass.async_create_task(_auto_analyze_when_ready(full_path, clean_name, int(duration or 0)))
            
        except Exception as e:
            log_to_file(f"Error in save_recording: {e}")

    hass.services.async_register(DOMAIN, "save_recording", handle_save_recording)
    
    # Return handle_save_recording for motion handlers
    _registered_handlers = {"handle_save_recording": handle_save_recording}

    async def _analyze_batch(
        *,
        device: str,
        objects: list[str],
        since_days: int | None = None,
        limit: int | None = None,
        skip_existing: bool = True,
        camera: str | None = None,
    ) -> int:
        """Batch analyze recordings with rate limiting."""
        now_ts = datetime.datetime.now().timestamp()
        cutoff = None
        if since_days is not None and since_days > 0:
            cutoff = now_ts - (since_days * 86400)

        files = await hass.async_add_executor_job(_list_video_files, storage_path, camera)
        if cutoff is not None:
            files = [f for f in files if os.path.getmtime(f) >= cutoff]

        if skip_existing:
            existing = await hass.async_add_executor_job(_build_analysis_index, analysis_output_path)
            files = [f for f in files if f not in existing]

        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        if limit and limit > 0:
            files = files[:limit]

        people_data = await _load_people_db(people_db_path)
        people = people_data.get("people", [])

        semaphore = _get_analysis_semaphore()

        processed = 0
        for path in files:
            async with semaphore:
                try:
                    perf_snapshot = get_sensor_snapshot_func()
                    
                    cam_name = _extract_camera_name_from_path(path)
                    cam_detector_conf = config_data.get(f"detector_confidence_{cam_name}", 0)
                    cam_face_conf = config_data.get(f"face_confidence_{cam_name}", 0)
                    cam_face_threshold = config_data.get(f"face_match_threshold_{cam_name}", 0)
                    
                    detector_conf_to_use = cam_detector_conf if cam_detector_conf > 0 else analysis_detector_confidence
                    face_conf_to_use = cam_face_conf if cam_face_conf > 0 else analysis_face_confidence
                    face_threshold_to_use = cam_face_threshold if cam_face_threshold > 0 else analysis_face_match_threshold
                    
                    cam_objects = config_data.get(f"analysis_objects_{cam_name}", [])
                    objects_to_use = cam_objects if cam_objects else objects
                    
                    result = await analyze_recording(
                        video_path=path,
                        output_root=analysis_output_path,
                        objects=objects_to_use,
                        device=device,
                        interval_s=analysis_frame_interval,
                        perf_snapshot=perf_snapshot,
                        detector_url=analysis_detector_url,
                        detector_confidence=detector_conf_to_use,
                        face_enabled=analysis_face_enabled,
                        face_confidence=face_conf_to_use,
                        face_match_threshold=face_threshold_to_use,
                        face_store_embeddings=analysis_face_store_embeddings,
                        people_db=people,
                        face_detector_url=analysis_detector_url,
                    )
                    if person_entities_enabled and result:
                        updated = update_person_entities_func(result)
                        if not updated:
                            update_person_entities_for_video_func(result.get("video_path"))
                    processed += 1
                except Exception as e:
                    log_to_file(f"Batch analysis error for {path}: {e}")
            await asyncio.sleep(0)

        return processed

    async def handle_analyze_recording(call: ServiceCall):
        """Analyze a recording offline and store results."""
        if not analysis_enabled:
            log_to_file("Analysis is disabled in settings")
            return

        media_id = call.data.get("media_id", "")
        objects = call.data.get("objects") or analysis_objects
        device = call.data.get("device") or analysis_device

        try:
            if "local/" in media_id:
                relative_path = media_id.split("local/", 1)[1]
                video_path = f"/media/{relative_path}"
            else:
                log_to_file(f"Unknown media_id format: {media_id}")
                return

            if not os.path.exists(video_path):
                log_to_file(f"Video not found: {video_path}")
                return

            output_dir = analysis_output_path
            
            cam_name = _extract_camera_name_from_path(video_path)
            cam_detector_conf = config_data.get(f"detector_confidence_{cam_name}", 0)
            cam_face_conf = config_data.get(f"face_confidence_{cam_name}", 0)
            cam_face_threshold = config_data.get(f"face_match_threshold_{cam_name}", 0)
            cam_objects = config_data.get(f"analysis_objects_{cam_name}", [])
            
            detector_conf_to_use = cam_detector_conf if cam_detector_conf > 0 else analysis_detector_confidence
            face_conf_to_use = cam_face_conf if cam_face_conf > 0 else analysis_face_confidence
            face_threshold_to_use = cam_face_threshold if cam_face_threshold > 0 else analysis_face_match_threshold
            objects_to_use = cam_objects if cam_objects else objects

            async def _run_analysis():
                try:
                    perf_snapshot = get_sensor_snapshot_func()
                    people_data = await _load_people_db(people_db_path)
                    people = people_data.get("people", [])
                    result = await analyze_recording(
                        video_path=video_path,
                        output_root=output_dir,
                        objects=objects_to_use,
                        device=device,
                        interval_s=analysis_frame_interval,
                        perf_snapshot=perf_snapshot,
                        detector_url=analysis_detector_url,
                        detector_confidence=detector_conf_to_use,
                        face_enabled=analysis_face_enabled,
                        face_confidence=face_conf_to_use,
                        face_match_threshold=face_threshold_to_use,
                        face_store_embeddings=analysis_face_store_embeddings,
                        people_db=people,
                        face_detector_url=analysis_detector_url,
                    )
                    if person_entities_enabled and result:
                        updated = update_person_entities_func(result)
                        if not updated:
                            update_person_entities_for_video_func(result.get("video_path"))
                    log_to_file(f"Analysis completed: {result.get('status') if result else 'no result'} -> {output_dir}")
                except Exception as e:
                    log_to_file(f"Error analyzing recording: {e}")

            hass.async_create_task(_run_analysis())
            log_to_file(f"Analysis queued: {video_path}")
        except Exception as e:
            log_to_file(f"Error analyzing recording: {e}")

    hass.services.async_register(DOMAIN, "analyze_recording", handle_analyze_recording)

    async def handle_analyze_all_recordings(call: ServiceCall):
        """Analyze all recordings matching filters."""
        if not analysis_enabled:
            log_to_file("Analysis is disabled in settings")
            return

        objects = call.data.get("objects") or analysis_objects
        device = call.data.get("device") or analysis_device
        since_days = call.data.get("since_days")
        limit = call.data.get("limit")
        skip_existing = call.data.get("skip_existing", True)
        camera = call.data.get("camera")

        processed = await _analyze_batch(
            device=device,
            objects=objects,
            since_days=since_days,
            limit=limit,
            skip_existing=skip_existing,
            camera=camera,
        )
        log_to_file(f"Analyze all completed: {processed} files")

    hass.services.async_register(DOMAIN, "analyze_all_recordings", handle_analyze_all_recordings)
    
    async def handle_delete_recording(call: ServiceCall):
        """Delete a recording and its thumbnail."""
        media_id = call.data.get("media_id", "")
        log_to_file(f"Delete recording requested: {media_id}")
        
        try:
            video_path = _validate_media_path(media_id)
            if not video_path:
                log_to_file(f"Invalid or unsafe media_id rejected: {media_id}")
                return
            
            if os.path.exists(video_path):
                os.remove(video_path)
                log_to_file(f"Deleted video: {video_path}")
            else:
                log_to_file(f"Video not found: {video_path}")
            
            filename = os.path.basename(video_path).replace('.mp4', '.jpg')
            parts = video_path.split('/')
            if len(parts) >= 2:
                cam_folder = parts[-2]
                thumb_path = os.path.join(snapshot_path_base, cam_folder, filename)
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                    log_to_file(f"Deleted thumbnail: {thumb_path}")
            
        except Exception as e:
            log_to_file(f"Error deleting recording: {e}")
            raise

    hass.services.async_register(DOMAIN, "delete_recording", handle_delete_recording)
    
    async def handle_delete_all_recordings(call: ServiceCall):
        """Delete all recordings, optionally filtered by camera and/or age."""
        camera = call.data.get("camera")
        older_than_days = call.data.get("older_than_days", 0)
        include_analysis = call.data.get("include_analysis", False)
        confirm = call.data.get("confirm", False)
        
        if not confirm:
            log_to_file("Delete all recordings: Missing confirmation flag")
            raise HomeAssistantError("Sicherheitsabfrage: Setze 'confirm: true' um zu bestätigen")
        
        log_to_file(f"Delete all recordings: camera={camera}, older_than_days={older_than_days}, include_analysis={include_analysis}")
        
        deleted_videos = 0
        deleted_thumbs = 0
        deleted_analysis = 0
        errors = []
        
        try:
            cutoff_date = None
            if older_than_days > 0:
                cutoff_date = datetime.datetime.now() - timedelta(days=older_than_days)
            
            if camera:
                safe_camera = camera.replace("..", "").replace("/", "_")
                video_pattern = os.path.join(storage_path, safe_camera, "*.mp4")
            else:
                video_pattern = os.path.join(storage_path, "*", "*.mp4")
            
            video_files = glob.glob(video_pattern)
            
            for video_path in video_files:
                try:
                    if cutoff_date:
                        filename = os.path.basename(video_path)
                        match = re.search(r'(\d{8})_(\d{6})', filename)
                        if match:
                            date_str = match.group(1)
                            file_date = datetime.datetime.strptime(date_str, "%Y%m%d")
                            if file_date >= cutoff_date:
                                continue
                    
                    os.remove(video_path)
                    deleted_videos += 1
                    
                    filename = os.path.basename(video_path).replace('.mp4', '.jpg')
                    cam_folder = os.path.basename(os.path.dirname(video_path))
                    thumb_path = os.path.join(snapshot_path_base, cam_folder, filename)
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
                        deleted_thumbs += 1
                        
                except Exception as e:
                    errors.append(f"{video_path}: {str(e)}")
            
            if include_analysis:
                analysis_base = os.path.join(storage_path, "_analysis")
                if os.path.exists(analysis_base):
                    analysis_dirs = glob.glob(os.path.join(analysis_base, "analysis_*"))
                    for analysis_dir in analysis_dirs:
                        try:
                            if cutoff_date:
                                dir_name = os.path.basename(analysis_dir)
                                match = re.search(r'analysis_(\d{8})', dir_name)
                                if match:
                                    date_str = match.group(1)
                                    dir_date = datetime.datetime.strptime(date_str, "%Y%m%d")
                                    if dir_date >= cutoff_date:
                                        continue
                            
                            import shutil
                            shutil.rmtree(analysis_dir)
                            deleted_analysis += 1
                        except Exception as e:
                            errors.append(f"{analysis_dir}: {str(e)}")
            
            log_to_file(f"Deleted: {deleted_videos} videos, {deleted_thumbs} thumbs, {deleted_analysis} analysis folders. Errors: {len(errors)}")
            
        except Exception as e:
            log_to_file(f"Error in delete_all_recordings: {e}")
            raise
        
        return {
            "deleted_videos": deleted_videos,
            "deleted_thumbnails": deleted_thumbs,
            "deleted_analysis": deleted_analysis,
            "errors": errors[:10]
        }

    hass.services.async_register(DOMAIN, "delete_all_recordings", handle_delete_all_recordings)
    
    # Store analyze_batch for scheduler access
    _registered_handlers["analyze_batch"] = _analyze_batch
    
    return _registered_handlers
