"""Service handlers for RTSP Recorder.

This module contains all HA service handlers, extracted from __init__.py
to improve maintainability (HIGH-001 Fix from Audit Report v1.0.7).

Services:
- save_recording: Record a stream (manual or motion-triggered)
- analyze_recording: Analyze a single recording
- analyze_all_recordings: Batch analyze multiple recordings
- delete_recording: Delete a single recording and its thumbnail
- delete_all_recordings: Bulk delete with optional filters

v1.1.0k: Added automatic analysis folder cleanup when deleting videos.
"""
import os
import re
import glob
import asyncio
import datetime
import time
from datetime import timedelta
from typing import Any, Callable

from .retention import delete_analysis_for_video

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


# v1.1.0: Metrics System for performance measurement
def record_metric(name: str, camera: str, start_time: float, extra_info: str = "") -> float:
    """Record a performance metric to the debug log.
    
    Format: METRIC|<camera>|<metric_name>|<elapsed>s[|<extra_info>]
    
    Args:
        name: Metric name (e.g., 'recording_to_saved', 'analysis_duration')
        camera: Camera name
        start_time: time.time() value when the operation started
        extra_info: Optional additional info to append
        
    Returns:
        Elapsed time in seconds
    """
    elapsed = time.time() - start_time
    if extra_info:
        log_to_file(f"METRIC|{camera}|{name}|{elapsed:.3f}s|{extra_info}")
    else:
        log_to_file(f"METRIC|{camera}|{name}|{elapsed:.3f}s")
    return elapsed


# Global batch analysis progress tracking
_batch_analysis_progress = {
    "running": False,
    "total": 0,
    "current": 0,
    "current_file": "",
    "started_at": None,
}

# Global single analysis progress tracking
_single_analysis_progress = {
    "running": False,
    "media_id": "",
    "video_path": "",
    "started_at": None,
    "completed": False,
}

# v1.1.0: Global recording progress tracking - supports multiple simultaneous recordings
# Key = video_path, Value = recording info dict
_active_recordings = {}


def get_batch_analysis_progress() -> dict:
    """Get current batch analysis progress (for WebSocket handler)."""
    return dict(_batch_analysis_progress)


def get_single_analysis_progress() -> dict:
    """Get current single analysis progress (for WebSocket handler)."""
    return dict(_single_analysis_progress)


def get_recording_progress() -> dict:
    """Get current recording progress (for WebSocket handler).
    
    Returns dict with:
    - running: True if any recording is active
    - count: Number of active recordings
    - recordings: List of active recording info dicts
    """
    recordings = list(_active_recordings.values())
    return {
        "running": len(recordings) > 0,
        "count": len(recordings),
        "recordings": recordings
    }


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
    analysis_overlay_smoothing: bool,
    analysis_overlay_smoothing_alpha: float,
    analysis_face_store_embeddings: bool,
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
        analysis_overlay_smoothing: Enable overlay smoothing
        analysis_overlay_smoothing_alpha: Overlay smoothing alpha
        analysis_face_store_embeddings: Store face embeddings
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

    async def handle_save_recording(call: ServiceCall = None, camera_name: str = None, duration: int = 30, snapshot_delay: float = 0) -> None:
        """Handle recording. Can be called via Service (manual) or Internal Event (auto)."""
        # v1.1.0 METRICS: Track total pipeline time from start
        pipeline_start = time.time()
        
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

            # v1.1.0: Add to active recordings for UI display
            global _active_recordings
            _active_recordings[full_path] = {
                "camera": clean_name,
                "video_path": full_path,
                "duration": duration,
                "started_at": datetime.datetime.now().isoformat(),
            }
            
            # v1.1.0: Fire event immediately so thumbnail appears in timeline
            hass.bus.async_fire("rtsp_recorder_recording_started", {
                "camera": clean_name,
                "video_path": full_path,
                "duration": duration,
                "timestamp": timestamp,
            })
            log_to_file(f"Fired rtsp_recorder_recording_started event for {clean_name}")

            if use_rtsp:
                # v1.1.0 OPTIMIZED: Event-based recording completion (not polling)
                recording_complete = asyncio.Event()
                recording_result = {"success": False, "error": None}
                
                def on_recording_complete(path: str, success: bool, error_msg: str | None) -> None:
                    """Callback when FFmpeg finishes and file is renamed."""
                    recording_result["success"] = success
                    recording_result["error"] = error_msg
                    recording_complete.set()
                    log_to_file(f"Recording callback: success={success}, error={error_msg}")
                
                # Start recording with callback (returns immediately)
                process = await async_record_stream(hass, rtsp_url, duration, full_path, on_complete=on_recording_complete)
                log_to_file(f"Recording started, waiting for completion via callback...")
                
                # v1.1.0 OPTIMIZED: Start snapshot task in parallel (after snapshot_delay)
                # Snapshot runs DURING recording, not after - saves time!
                snap_folder = os.path.join(snapshot_path_base, clean_name)
                if not os.path.exists(snap_folder):
                    os.makedirs(snap_folder, exist_ok=True)
                snap_filename = f"{clean_name}_{timestamp}.jpg"
                snap_full_path = os.path.join(snap_folder, snap_filename)
                
                async def take_snapshot_parallel():
                    """Take snapshot after configured delay (runs parallel to recording)."""
                    try:
                        if snapshot_delay > 0:
                            log_to_file(f"Snapshot scheduled in {snapshot_delay}s (parallel to recording)")
                            await asyncio.sleep(snapshot_delay)
                        log_to_file(f"Taking parallel snapshot: {snap_full_path}")
                        await async_take_snapshot(hass, rtsp_url, snap_full_path, delay=0)
                        log_to_file(f"Parallel snapshot complete: {snap_full_path}")
                    except Exception as e:
                        log_to_file(f"Parallel snapshot error: {e}")
                
                # Start snapshot task (runs in parallel)
                snapshot_task = hass.async_create_task(take_snapshot_parallel())
                
                # Wait for recording to complete (event-based, not polling!)
                # Timeout = duration + 30s safety buffer
                try:
                    await asyncio.wait_for(recording_complete.wait(), timeout=duration + 30)
                    if recording_result["success"]:
                        log_to_file(f"Recording completed successfully via callback")
                    else:
                        log_to_file(f"Recording completed with error: {recording_result['error']}")
                except asyncio.TimeoutError:
                    log_to_file(f"WARNING: Recording callback timeout after {duration + 30}s, checking file...")
                    # Fallback: Check if file exists anyway
                    if os.path.exists(full_path):
                        log_to_file(f"File exists despite timeout, continuing")
                    else:
                        log_to_file(f"ERROR: Recording failed - file not found")
                
                # Wait for snapshot to complete (if still running)
                try:
                    await asyncio.wait_for(asyncio.shield(snapshot_task), timeout=10)
                except asyncio.TimeoutError:
                    log_to_file(f"Snapshot task still running, continuing without waiting")
                except Exception:
                    pass  # Snapshot task may have completed already
                
                log_to_file(f"Recording and snapshot complete")
            else:
                # v1.1.0 OPTIMIZED: Parallel snapshot for HA Camera entities too
                snap_folder = os.path.join(snapshot_path_base, clean_name)
                if not os.path.exists(snap_folder):
                    os.makedirs(snap_folder, exist_ok=True)
                snap_filename = f"{clean_name}_{timestamp}.jpg"
                snap_full_path = os.path.join(snap_folder, snap_filename)
                
                async def take_ha_snapshot_parallel():
                    """Take HA camera snapshot after configured delay (parallel to recording)."""
                    try:
                        if snapshot_delay > 0:
                            log_to_file(f"HA Snapshot scheduled in {snapshot_delay}s (parallel to recording)")
                            await asyncio.sleep(snapshot_delay)
                        log_to_file(f"Taking parallel HA snapshot: {snap_full_path}")
                        await hass.services.async_call("camera", "snapshot", {
                            "entity_id": entity_id,
                            "filename": snap_full_path
                        })
                        log_to_file(f"Parallel HA snapshot complete: {snap_full_path}")
                    except Exception as e:
                        log_to_file(f"Parallel HA snapshot error: {e}")
                
                # Start snapshot task in parallel
                snapshot_task = hass.async_create_task(take_ha_snapshot_parallel())
                
                await hass.services.async_call("camera", "record", {
                    "entity_id": entity_id,
                    "filename": full_path,
                    "duration": duration,
                    "lookback": 0
                })
                # HA camera.record returns immediately, wait for recording duration
                # v1.1.0 OPTIMIZED: Reduced from +2s to +1s - files are usually ready sooner
                log_to_file(f"HA camera recording started, waiting {duration}s...")
                await asyncio.sleep(duration + 1)
                
                # v1.1.0 OPTIMIZED: Faster file check - 0.5s intervals, max 10s wait
                max_wait_file = 20  # 20 * 0.5s = 10s max
                for i in range(max_wait_file):
                    if os.path.exists(full_path):
                        log_to_file(f"Recording file ready: {full_path}")
                        break
                    await asyncio.sleep(0.5)
                else:
                    log_to_file(f"WARNING: File not found after {max_wait_file * 0.5}s: {full_path}")
                
                # Wait for snapshot to complete (if still running)
                try:
                    await asyncio.wait_for(asyncio.shield(snapshot_task), timeout=10)
                except asyncio.TimeoutError:
                    log_to_file(f"HA Snapshot task still running, continuing")
                except Exception:
                    pass
                    
                log_to_file(f"HA camera recording and snapshot complete")

            # v1.1.0: Recording + Snapshot finished - NOW remove from active recordings
            # This triggers the frontend to refresh the timeline
            if full_path in _active_recordings:
                del _active_recordings[full_path]
            
            # v1.1.0 METRICS: Record time from start to saved
            record_metric("recording_to_saved", clean_name, pipeline_start, f"duration={duration}s")
            
            # v1.1.0: Fire event so frontend can refresh
            hass.bus.async_fire("rtsp_recorder_recording_saved", {
                "camera": clean_name,
                "video_path": full_path,
                "snapshot_path": snap_full_path,
                "timestamp": timestamp,
            })
            log_to_file(f"Fired rtsp_recorder_recording_saved event for {clean_name}")

            # 3. Auto-Analyze after recording
            if analysis_enabled and analysis_auto_new:
                async def _auto_analyze_when_ready(path: str, cam_name: str, rec_duration: int):
                    global _single_analysis_progress
                    # v1.1.0 METRICS: Track analysis duration
                    analysis_start = time.time()
                    
                    try:
                        # v1.1.0 OPTIMIZED: Faster file stability check (1s intervals, 2 checks = 2s)
                        ready = await _wait_for_file_ready(path, max_wait_s=20, stable_checks=2, interval_s=1)
                        if not ready:
                            log_to_file(f"Recording not ready for auto-analysis (timeout): {path}")
                            return

                        log_to_file(f"Auto-analyzing new recording: {path}")
                        
                        # v1.1.0: Set progress for footer display
                        analysis_started_at = datetime.datetime.now().isoformat()
                        _single_analysis_progress = {
                            "running": True,
                            "media_id": "",
                            "video_path": path,
                            "started_at": analysis_started_at,
                            "completed": False,
                        }
                        
                        # v1.1.0f: Fire event so frontend shows analysis indicator (PUSH)
                        log_to_file(f"PUSH: Firing analysis_started event for {cam_name}")
                        hass.bus.async_fire("rtsp_recorder_analysis_started", {
                            "video_path": path,
                            "camera": cam_name,
                            "started_at": analysis_started_at,
                        })
                        
                        perf_snapshot = get_sensor_snapshot_func()
                        semaphore = _get_analysis_semaphore()

                        cam_objects_key = f"analysis_objects_{cam_name}"
                        cam_specific_objects = config_data.get(cam_objects_key, [])
                        objects_to_use = cam_specific_objects if cam_specific_objects else analysis_objects

                        cam_detector_conf = config_data.get(f"detector_confidence_{cam_name}", 0)
                        cam_face_conf = config_data.get(f"face_confidence_{cam_name}", 0)
                        cam_face_threshold = config_data.get(f"face_match_threshold_{cam_name}", 0)
                        
                        detector_conf_to_use = cam_detector_conf if cam_detector_conf > 0 else analysis_detector_confidence
                        face_conf_to_use = cam_face_conf if cam_face_conf > 0 else analysis_face_confidence
                        face_threshold_to_use = cam_face_threshold if cam_face_threshold > 0 else analysis_face_match_threshold

                        people_data = await _load_people_db()
                        people = people_data.get("people", [])
                        auto_device = await resolve_auto_device_func()
                        async with semaphore:
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
                                overlay_smoothing=analysis_overlay_smoothing,
                                overlay_smoothing_alpha=analysis_overlay_smoothing_alpha,
                                face_store_embeddings=analysis_face_store_embeddings,
                                people_db=people,
                                face_detector_url=analysis_detector_url,
                            )
                        if person_entities_enabled:
                            try:
                                updated = update_person_entities_func(result or {})
                                if not updated:
                                    await update_person_entities_for_video_func(path)
                            except Exception:
                                pass
                        
                        # v1.1.0 METRICS: Record analysis duration
                        record_metric("analysis_duration", cam_name, analysis_start)
                        # v1.1.0 METRICS: Record total pipeline time (from pipeline_start captured in closure)
                        record_metric("total_pipeline_time", cam_name, pipeline_start, f"rec={rec_duration}s")
                        
                        log_to_file(f"Auto-analysis completed for: {path}")
                        # v1.1.0: Mark as completed
                        _single_analysis_progress["running"] = False
                        _single_analysis_progress["completed"] = True
                        
                        # v1.1.0f: Fire event so frontend updates (PUSH)
                        log_to_file(f"PUSH: Firing analysis_completed event for {cam_name}")
                        hass.bus.async_fire("rtsp_recorder_analysis_completed", {
                            "video_path": path,
                            "camera": cam_name,
                            "completed_at": datetime.datetime.now().isoformat(),
                        })
                    except Exception as ae:
                        log_to_file(f"Auto-analysis error: {ae}")
                        # v1.1.0: Mark as failed
                        _single_analysis_progress["running"] = False
                        _single_analysis_progress["completed"] = False

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
        global _batch_analysis_progress
        
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

        # Initialize progress tracking
        _batch_analysis_progress = {
            "running": True,
            "total": len(files),
            "current": 0,
            "current_file": "",
            "started_at": datetime.datetime.now().isoformat(),
        }

        people_data = await _load_people_db()
        people = people_data.get("people", [])

        semaphore = _get_analysis_semaphore()

        processed = 0
        for path in files:
            # Update progress
            _batch_analysis_progress["current"] = processed
            _batch_analysis_progress["current_file"] = os.path.basename(path)
            
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
                        device=auto_device,
                        interval_s=analysis_frame_interval,
                        perf_snapshot=perf_snapshot,
                        detector_url=analysis_detector_url,
                        detector_confidence=detector_conf_to_use,
                        face_enabled=analysis_face_enabled,
                        face_confidence=face_conf_to_use,
                        face_match_threshold=face_threshold_to_use,
                        overlay_smoothing=analysis_overlay_smoothing,
                        overlay_smoothing_alpha=analysis_overlay_smoothing_alpha,
                        face_store_embeddings=analysis_face_store_embeddings,
                        people_db=people,
                        face_detector_url=analysis_detector_url,
                    )
                    if person_entities_enabled and result:
                        updated = update_person_entities_func(result)
                        if not updated:
                            await update_person_entities_for_video_func(result.get("video_path"))
                    processed += 1
                except Exception as e:
                    log_to_file(f"Batch analysis error for {path}: {e}")
            await asyncio.sleep(0)

        # Mark progress as complete
        _batch_analysis_progress["current"] = processed
        _batch_analysis_progress["running"] = False
        _batch_analysis_progress["current_file"] = ""
        
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
                global _single_analysis_progress
                analysis_started_at = datetime.datetime.now().isoformat()
                # Set progress to running
                _single_analysis_progress = {
                    "running": True,
                    "media_id": media_id,
                    "video_path": video_path,
                    "started_at": analysis_started_at,
                    "completed": False,
                }
                
                # v1.1.0n: Fire analysis_started event for manual analysis (same as auto-analysis)
                log_to_file(f"PUSH: Firing analysis_started event for manual analysis: {cam_name}")
                hass.bus.async_fire("rtsp_recorder_analysis_started", {
                    "video_path": video_path,
                    "camera": cam_name,
                    "started_at": analysis_started_at,
                })
                
                try:
                    perf_snapshot = get_sensor_snapshot_func()
                    people_data = await _load_people_db()
                    people = people_data.get("people", [])
                    semaphore = _get_analysis_semaphore()
                    async with semaphore:
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
                            overlay_smoothing=analysis_overlay_smoothing,
                            overlay_smoothing_alpha=analysis_overlay_smoothing_alpha,
                            face_store_embeddings=analysis_face_store_embeddings,
                            people_db=people,
                            face_detector_url=analysis_detector_url,
                        )
                    if person_entities_enabled and result:
                        updated = update_person_entities_func(result)
                        if not updated:
                            await update_person_entities_for_video_func(result.get("video_path"))
                    log_to_file(f"Analysis completed: {result.get('status') if result else 'no result'} -> {output_dir}")
                    # Mark as completed
                    _single_analysis_progress["running"] = False
                    _single_analysis_progress["completed"] = True
                    
                    # v1.1.0n: Fire analysis_completed event for manual analysis
                    log_to_file(f"PUSH: Firing analysis_completed event for manual analysis: {cam_name}")
                    hass.bus.async_fire("rtsp_recorder_analysis_completed", {
                        "video_path": video_path,
                        "camera": cam_name,
                        "completed_at": datetime.datetime.now().isoformat(),
                    })
                except Exception as e:
                    log_to_file(f"Error analyzing recording: {e}")
                    _single_analysis_progress["running"] = False
                    _single_analysis_progress["completed"] = False
                    
                    # v1.1.0n: Fire analysis_completed event even on error (so UI clears)
                    hass.bus.async_fire("rtsp_recorder_analysis_completed", {
                        "video_path": video_path,
                        "camera": cam_name,
                        "completed_at": datetime.datetime.now().isoformat(),
                        "error": str(e),
                    })

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
            
            # v1.1.0k: Delete associated analysis folder first (before video is gone)
            if os.path.exists(video_path):
                deleted_analysis = delete_analysis_for_video(video_path, storage_path)
                if deleted_analysis:
                    log_to_file(f"Deleted analysis for: {video_path}")
            
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
