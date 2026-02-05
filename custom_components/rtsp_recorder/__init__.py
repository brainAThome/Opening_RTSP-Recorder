"""RTSP Recorder Integration.

This is the main integration file that handles:
- Home Assistant setup and configuration
- Motion listener registration
- Scheduled cleanup and auto-analysis
- WebSocket and Service registration (via imported modules)

HIGH-001 Fix: Modularized from 1619 lines to ~450 lines.
WebSocket handlers moved to websocket_handlers.py
Service handlers moved to services.py
"""
import logging
import os
import re
import traceback
import asyncio
import datetime
from datetime import timedelta
from typing import Any

import aiohttp
from aiohttp import web
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.event import async_track_state_change_event

# Internal modules
from .retention import cleanup_recordings, cleanup_analysis_data
from .analysis import detect_available_devices

# Modularized Imports
from .const import (
    DOMAIN,
    DEFAULT_MAX_CONCURRENT_ANALYSES,
)
from .helpers import (
    log_to_file,
    _validate_person_name,
    _parse_hhmm,
    _set_analysis_semaphore_limit,
)
from .people_db import (
    _load_people_db,
    enable_sqlite_backend,
    disable_sqlite_backend,
    is_sqlite_enabled,
    log_recognition_event,  # v1.1.0: Movement profile
)
from .analysis_helpers import _find_analysis_for_video

# NEW: Modularized handlers (HIGH-001 Fix)
from .websocket_handlers import register_websocket_handlers, register_people_websocket_handlers
from .services import register_services

_LOGGER = logging.getLogger(__name__)


class ThumbnailView(HomeAssistantView):
    """HTTP View to serve thumbnails from any configured path."""
    
    url = "/api/rtsp_recorder/thumbnail/{camera}/{filename}"
    name = "api:rtsp_recorder:thumbnail"
    requires_auth = False  # Thumbnails are not sensitive
    
    def __init__(self, snapshot_path: str):
        """Initialize with the configured snapshot path."""
        self._snapshot_path = snapshot_path
    
    async def get(self, request: web.Request, camera: str, filename: str) -> web.Response:
        """Handle thumbnail request."""
        # Security: Prevent path traversal
        if ".." in camera or ".." in filename or "/" in filename or "\\" in filename:
            return web.Response(status=403, text="Forbidden")
        
        # Build full path
        file_path = os.path.join(self._snapshot_path, camera, filename)
        
        # Read file in executor to avoid blocking the event loop
        def _read_file():
            if not os.path.isfile(file_path):
                return None
            with open(file_path, "rb") as f:
                return f.read()
        
        # Determine content type
        content_type = "image/jpeg"
        if filename.lower().endswith(".png"):
            content_type = "image/png"
        elif filename.lower().endswith(".webp"):
            content_type = "image/webp"
        
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, _read_file)
            if data is None:
                return web.Response(status=404, text="Not found")
            return web.Response(body=data, content_type=content_type)
        except Exception as e:
            _LOGGER.error(f"Error reading thumbnail {file_path}: {e}")
            return web.Response(status=500, text="Internal error")


async def async_setup(hass, config):
    """Set up the RTSP Recorder component."""
    return True


async def async_setup_entry(hass: ConfigEntry, entry: ConfigEntry):
    """Set up RTSP Recorder from a config entry."""
    log_to_file(f"START: Setting up RTSP Recorder entry {entry.entry_id}")
    
    # Merge data and options
    config_data = {**entry.data, **entry.options}
    
    # Extract configuration values
    storage_path = config_data.get("storage_path", "/media/rtsp_recordings")
    snapshot_path_base = config_data.get("snapshot_path", "/config/www/thumbnails")
    retention_days = config_data.get("retention_days", 7)
    snapshot_retention_days = config_data.get("snapshot_retention_days", 7)
    retention_hours = config_data.get("retention_hours", 0)
    cleanup_interval_hours = int(config_data.get("cleanup_interval_hours", 24))
    analysis_enabled = config_data.get("analysis_enabled", True)
    analysis_device = config_data.get("analysis_device", "cpu")
    analysis_objects = config_data.get("analysis_objects", ["person"])
    analysis_output_path = config_data.get("analysis_output_path", os.path.join(storage_path, "_analysis"))
    analysis_frame_interval = int(config_data.get("analysis_frame_interval", 2))
    analysis_max_concurrent = int(config_data.get("analysis_max_concurrent", DEFAULT_MAX_CONCURRENT_ANALYSES))
    analysis_detector_url = config_data.get("analysis_detector_url", "")
    analysis_detector_confidence = float(config_data.get("analysis_detector_confidence", 0.4))
    analysis_face_enabled = bool(config_data.get("analysis_face_enabled", False))
    analysis_face_confidence = float(config_data.get("analysis_face_confidence", 0.2))
    analysis_face_match_threshold = float(config_data.get("analysis_face_match_threshold", 0.35))
    analysis_overlay_smoothing = bool(config_data.get("analysis_overlay_smoothing", False))
    analysis_overlay_smoothing_alpha = float(config_data.get("analysis_overlay_smoothing_alpha", 0.35))
    analysis_face_store_embeddings = bool(config_data.get("analysis_face_store_embeddings", True))
    analysis_auto_enabled = config_data.get("analysis_auto_enabled", False)
    analysis_auto_mode = config_data.get("analysis_auto_mode", "daily")
    analysis_auto_time = config_data.get("analysis_auto_time", "03:00")
    analysis_auto_interval_hours = int(config_data.get("analysis_auto_interval_hours", 24))
    analysis_auto_since_days = int(config_data.get("analysis_auto_since_days", 1))
    analysis_auto_limit = int(config_data.get("analysis_auto_limit", 50))
    analysis_auto_skip_existing = bool(config_data.get("analysis_auto_skip_existing", True))
    analysis_auto_new = bool(config_data.get("analysis_auto_new", False))
    analysis_auto_force_coral = bool(config_data.get("analysis_auto_force_coral", False))
    person_entities_enabled = bool(config_data.get("person_entities_enabled", False))
    analysis_perf_cpu_entity = config_data.get("analysis_perf_cpu_entity")
    analysis_perf_igpu_entity = config_data.get("analysis_perf_igpu_entity")
    analysis_perf_coral_entity = config_data.get("analysis_perf_coral_entity")

    # Apply max concurrent analyses limit
    _set_analysis_semaphore_limit(analysis_max_concurrent)
    
    # Build override map for per-camera retention
    known_settings = [
        "storage_path", "snapshot_path", "retention_days", "snapshot_retention_days",
        "retention_hours", "camera_filter", "analysis_enabled", "analysis_device",
        "analysis_objects", "analysis_output_path", "analysis_frame_interval",
        "analysis_max_concurrent",
        "analysis_detector_url", "analysis_detector_confidence", "analysis_face_enabled",
        "analysis_face_confidence", "analysis_face_match_threshold",
        "analysis_overlay_smoothing", "analysis_overlay_smoothing_alpha",
        "analysis_face_store_embeddings", "analysis_auto_enabled",
        "analysis_auto_mode", "analysis_auto_time", "analysis_auto_interval_hours",
        "analysis_auto_since_days", "analysis_auto_limit", "analysis_auto_skip_existing",
        "analysis_auto_new", "analysis_auto_force_coral", "person_entities_enabled",
        "analysis_perf_cpu_entity", "analysis_perf_igpu_entity", "analysis_perf_coral_entity",
    ]
    
    override_map = {}
    for key, value in config_data.items():
        if key in known_settings:
            continue
        if key.startswith("retention_hours_"):
            camera_name = key.replace("retention_hours_", "")
            if isinstance(value, (int, float)) and value > 0:
                override_map[camera_name] = value
            
    log_to_file(f"Config: Path={storage_path}, Video={retention_days}d, Snap={snapshot_retention_days}d")
    if override_map:
        log_to_file(f"Active Overrides: {override_map}")

    try:
        # Register dashboard resource
        add_extra_js_url(hass, "/local/rtsp-recorder-card.js")

        # 1. Ensure base folders exist
        if not os.path.exists(storage_path):
            os.makedirs(storage_path, exist_ok=True)
        if not os.path.exists(snapshot_path_base):
            os.makedirs(snapshot_path_base, exist_ok=True)
        if not os.path.exists(analysis_output_path):
            os.makedirs(analysis_output_path, exist_ok=True)

        # 2. Register HTTP endpoint for thumbnails (v1.0.9+)
        # This allows thumbnails to be served from any configured path
        hass.http.register_view(ThumbnailView(snapshot_path_base))
        log_to_file(f"Registered thumbnail endpoint: /api/rtsp_recorder/thumbnail/")

        # 3. Initialize SQLite database backend (v1.1.0j: SQLite-only)
        log_to_file("Enabling SQLite backend for people database...")
        if enable_sqlite_backend("/config"):
            log_to_file("SQLite backend enabled successfully")
        else:
            log_to_file("ERROR: SQLite backend initialization failed!")
        
        # Load people database from SQLite
        await _load_people_db()

        # ===== Helper functions needed by services =====
        
        def _sensor_snapshot() -> dict[str, Any]:
            """Get sensor values snapshot for analysis."""
            def _get_value(entity_id: str | None) -> dict[str, Any] | None:
                if not entity_id:
                    return None
                state = hass.states.get(entity_id)
                if not state:
                    return {"entity_id": entity_id, "state": None, "unit": None}
                return {
                    "entity_id": entity_id,
                    "state": state.state,
                    "unit": state.attributes.get("unit_of_measurement"),
                }
            return {
                "cpu": _get_value(analysis_perf_cpu_entity),
                "igpu": _get_value(analysis_perf_igpu_entity),
                "coral": _get_value(analysis_perf_coral_entity),
                "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S"),
            }

        async def _fetch_remote_devices(url: str) -> list[str]:
            """Fetch available devices from detector service."""
            if not url:
                return []
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{url.rstrip('/')}/info", timeout=5) as resp:
                        if resp.status != 200:
                            return []
                        data = await resp.json()
                        return data.get("devices", [])
            except Exception:
                return []

        async def _resolve_auto_device() -> str:
            """Resolve device for auto-analysis (prefer Coral if configured)."""
            if not analysis_auto_force_coral:
                return analysis_device
            devices = []
            if analysis_detector_url:
                devices = await _fetch_remote_devices(analysis_detector_url)
            if not devices:
                devices = await hass.async_add_executor_job(detect_available_devices)
            return "coral_usb" if "coral_usb" in devices else analysis_device

        # ===== Person entity helpers =====
        
        def _person_entity_id(name: str) -> str:
            """Generate entity ID for person."""
            slug = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower())
            slug = re.sub(r"_+", "_", slug).strip("_")
            return f"binary_sensor.rtsp_recorder_person_{slug or 'unknown'}"

        def _extract_camera_from_path(video_path: str | None) -> str | None:
            """Extract camera name from video path. v1.1.0: For person entity attributes."""
            if not video_path:
                return None
            parts = video_path.replace("\\", "/").split("/")
            if len(parts) >= 2:
                camera = parts[-2] if parts[-2] else parts[-1]
                return camera.replace("_", " ") if camera else None
            return None

        def _set_person_entity(name: str, similarity: float | None, video_path: str | None, camera: str | None):
            """Set person entity state."""
            if not person_entities_enabled:
                return
            entity_id = _person_entity_id(name)
            attrs = {
                "friendly_name": f"RTSP Person {name}" + (f" ({camera})" if camera else ""),  # v1.1.0: Show camera in history
                "person_name": name,
                "similarity": similarity,
                "camera": camera,
                "video_path": video_path,
                "last_seen": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            hass.states.async_set(entity_id, "on", attrs)
            
            # v1.1.0k: Log to recognition_history for movement profile
            try:
                hass.async_create_task(log_recognition_event(
                    camera_name=camera or "Unknown",
                    person_name=name,
                    confidence=similarity,
                    recording_path=video_path,
                    metadata={"source": "person_entity"}
                ))
                log_to_file(f"Logged recognition event: {name} at {camera}")
            except Exception as e:
                log_to_file(f"Failed to log recognition event: {e}")
            
            timers = hass.data.setdefault(DOMAIN, {}).setdefault("person_entity_timers", {})
            if entity_id in timers:
                try:
                    timers[entity_id].cancel()
                except Exception:
                    pass
            timers[entity_id] = hass.loop.call_later(10, lambda: hass.states.async_set(entity_id, "off", attrs))  # v1.1.0: Reduced from 30s

        def _extract_person_matches(result: dict) -> dict[str, dict[str, Any]]:
            """Extract person matches from analysis result."""
            matches: dict[str, dict[str, Any]] = {}

            def _add_match(name: str, similarity: float | None):
                if not name:
                    return
                prev = matches.get(name)
                if prev is None:
                    matches[name] = {"similarity": similarity}
                else:
                    prev_sim = prev.get("similarity")
                    if similarity is not None and (prev_sim is None or similarity > prev_sim):
                        matches[name]["similarity"] = similarity

            detections = result.get("detections") or []
            for det in detections:
                for face in (det.get("faces") or []):
                    match = face.get("match") or {}
                    name = match.get("name") or face.get("name") or face.get("person_name")
                    similarity = match.get("similarity") if match else face.get("similarity")
                    _add_match(name, similarity)

            for face in (result.get("faces") or []):
                match = face.get("match") or {}
                name = match.get("name") or face.get("name") or face.get("person_name")
                similarity = match.get("similarity") if match else face.get("similarity")
                _add_match(name, similarity)

            return matches

        def _update_person_entities_from_result(result: dict) -> bool:
            """Update person entities from analysis result. v1.1.0: Now includes camera info."""
            if not person_entities_enabled:
                return False
            matches = _extract_person_matches(result)
            if not matches:
                return False
            video_path = result.get("video_path")
            camera = _extract_camera_from_path(video_path)
            for name, info in matches.items():
                _set_person_entity(name, info.get("similarity"), video_path, camera)
            return True

        async def _update_person_entities_for_video(video_path: str | None):
            """Update person entities for a video."""
            if not person_entities_enabled or not video_path:
                return
            try:
                result = await hass.async_add_executor_job(_find_analysis_for_video, analysis_output_path, video_path)
                if result:
                    _update_person_entities_from_result(result)
            except Exception:
                pass

        # ===== Register Services (from services.py) =====
        
        service_handlers = register_services(
            hass=hass,
            entry=entry,
            config_data=config_data,
            storage_path=storage_path,
            snapshot_path_base=snapshot_path_base,
            analysis_output_path=analysis_output_path,
            analysis_detector_url=analysis_detector_url,
            analysis_frame_interval=analysis_frame_interval,
            analysis_objects=analysis_objects,
            analysis_device=analysis_device,
            analysis_enabled=analysis_enabled,
            analysis_auto_new=analysis_auto_new,
            analysis_detector_confidence=analysis_detector_confidence,
            analysis_face_enabled=analysis_face_enabled,
            analysis_face_confidence=analysis_face_confidence,
            analysis_face_match_threshold=analysis_face_match_threshold,
            analysis_overlay_smoothing=analysis_overlay_smoothing,
            analysis_overlay_smoothing_alpha=analysis_overlay_smoothing_alpha,
            analysis_face_store_embeddings=analysis_face_store_embeddings,
            person_entities_enabled=person_entities_enabled,
            get_sensor_snapshot_func=_sensor_snapshot,
            resolve_auto_device_func=_resolve_auto_device,
            update_person_entities_func=_update_person_entities_from_result,
            update_person_entities_for_video_func=_update_person_entities_for_video,
        )
        
        # Get handle_save_recording for motion handlers
        handle_save_recording = service_handlers["handle_save_recording"]
        _analyze_batch = service_handlers["analyze_batch"]

        # ===== Register Motion Listeners (Auto-Record) =====
        
        def _create_motion_handler(cam_name, record_duration, snap_delay):
            """Create closure for motion handler."""
            async def _motion_changed(event):
                new_state = event.data.get("new_state")
                old_state = event.data.get("old_state")
                old_state_val = old_state.state if old_state else "None"
                new_state_val = new_state.state if new_state else "None"
                log_to_file(f"Motion state change: {event.data['entity_id']} [{old_state_val} -> {new_state_val}]")
                if new_state and new_state.state == "on" and old_state and old_state.state != "on":
                    log_to_file(f"Motion detected on {event.data['entity_id']} -> Triggering {cam_name}")
                    await handle_save_recording(camera_name=cam_name, duration=record_duration, snapshot_delay=snap_delay)
            return _motion_changed

        for key, value in config_data.items():
            try:
                # v1.2.0: Support new multi-sensor format (sensors_) and legacy single sensor (sensor_)
                if key.startswith("sensors_"):
                    # New format: value is a list of entity IDs
                    camera_target = key.replace("sensors_", "")
                    motion_entities = value if isinstance(value, list) else [value]
                    
                    duration_key = f"duration_{camera_target}"
                    record_duration = config_data.get(duration_key, 120)
                    
                    delay_key = f"snapshot_delay_{camera_target}"
                    snap_delay = config_data.get(delay_key, 0)
                    
                    for motion_entity in motion_entities:
                        log_to_file(f"Setup Auto-Record: {motion_entity} -> {camera_target} ({record_duration}s, delay {snap_delay}s)")
                        
                        unsub = async_track_state_change_event(
                            hass, 
                            [motion_entity], 
                            _create_motion_handler(camera_target, record_duration, snap_delay)
                        )
                        entry.async_on_unload(unsub)
                        
                elif key.startswith("sensor_"):
                    # Legacy format: value is a single entity ID string
                    camera_target = key.replace("sensor_", "")
                    # Skip if new format already exists for this camera
                    if f"sensors_{camera_target}" in config_data:
                        continue
                        
                    motion_entity = value
                    
                    duration_key = f"duration_{camera_target}"
                    record_duration = config_data.get(duration_key, 120)
                    
                    delay_key = f"snapshot_delay_{camera_target}"
                    snap_delay = config_data.get(delay_key, 0)
                    
                    log_to_file(f"Setup Auto-Record (legacy): {motion_entity} -> {camera_target} ({record_duration}s, delay {snap_delay}s)")
                    
                    unsub = async_track_state_change_event(
                        hass, 
                        [motion_entity], 
                        _create_motion_handler(camera_target, record_duration, snap_delay)
                    )
                    entry.async_on_unload(unsub)
            except Exception as e:
                log_to_file(f"Error setting up auto-record for {key}: {e}")
                _LOGGER.error(f"Error setting up auto-record: {e}")

        # ===== Schedule Retention Cleanup =====
        
        async def run_cleanup(now=None):
            """Run scheduled retention cleanup."""
            log_to_file("Running scheduled retention cleanup...")
            
            # Cleanup old recordings
            await hass.async_add_executor_job(
                cleanup_recordings, 
                storage_path, 
                retention_days, 
                retention_hours,
                override_map
            )
            
            # Cleanup old snapshots
            await hass.async_add_executor_job(
                cleanup_recordings, 
                snapshot_path_base, 
                snapshot_retention_days, 
                0,
                override_map
            )
            
            # v1.1.0k: Cleanup old analysis data (same retention as videos)
            await hass.async_add_executor_job(
                cleanup_analysis_data,
                storage_path,
                retention_days,
                retention_hours,
            )

        # Run once on startup (after 30s delay)
        hass.loop.call_later(30, lambda: hass.async_create_task(run_cleanup()))
        
        # v1.1.0k: Configurable cleanup interval (default: 24h, min: 1h for short retentions)
        log_to_file(f"Cleanup interval: {cleanup_interval_hours}h")
        unsub_cleanup = async_track_time_interval(hass, run_cleanup, timedelta(hours=cleanup_interval_hours))
        entry.async_on_unload(unsub_cleanup)

        # ===== Auto Analysis Scheduler =====
        
        async def run_auto_analysis(now=None):
            """Run scheduled auto-analysis."""
            if not analysis_enabled or not analysis_auto_enabled:
                return
            try:
                auto_device = await _resolve_auto_device()
                processed = await _analyze_batch(
                    device=auto_device,
                    objects=analysis_objects,
                    since_days=analysis_auto_since_days,
                    limit=analysis_auto_limit,
                    skip_existing=analysis_auto_skip_existing,
                )
                log_to_file(f"Auto analysis run done: {processed} files")
            except Exception as e:
                log_to_file(f"Auto analysis failed: {e}")

        if analysis_enabled and analysis_auto_enabled:
            if analysis_auto_mode == "interval":
                interval_hours = max(1, int(analysis_auto_interval_hours or 24))
                unsub_analysis = async_track_time_interval(hass, run_auto_analysis, timedelta(hours=interval_hours))
                entry.async_on_unload(unsub_analysis)
            else:
                hhmm = _parse_hhmm(analysis_auto_time) or (3, 0)
                unsub_analysis = async_track_time_change(hass, run_auto_analysis, hour=hhmm[0], minute=hhmm[1], second=0)
                entry.async_on_unload(unsub_analysis)
        
        # Register update listener
        entry.async_on_unload(entry.add_update_listener(update_listener))

        # ===== Camera Health Watchdog =====
        
        # Track last recording time per camera
        camera_last_recording: dict[str, datetime.datetime] = {}
        camera_expected_activity: dict[str, bool] = {}  # Track if camera should be recording
        
        def _get_newest_recording(cam_folder: str) -> str | None:
            """Get newest recording file from camera folder (runs in executor)."""
            if not os.path.exists(cam_folder):
                return None
            try:
                files = [f for f in os.listdir(cam_folder) if f.endswith('.mp4')]
                if files:
                    files.sort(reverse=True)
                    return files[0]
            except OSError:
                pass
            return None
        
        async def check_camera_health(now=None):
            """Check if cameras are recording as expected."""
            try:
                loop = asyncio.get_event_loop()
                
                # v1.2.0: Get all configured cameras from motion sensors (both formats)
                cameras_to_check = {}  # camera_name -> list of motion entities
                
                for key, value in config_data.items():
                    if key.startswith("sensors_"):
                        # New format: list of entities
                        camera_name = key.replace("sensors_", "")
                        motion_entities = value if isinstance(value, list) else [value]
                        cameras_to_check[camera_name] = motion_entities
                    elif key.startswith("sensor_"):
                        # Legacy format: single entity
                        camera_name = key.replace("sensor_", "")
                        if camera_name not in cameras_to_check:  # Don't override new format
                            cameras_to_check[camera_name] = [value]
                
                for camera_name, motion_entities in cameras_to_check.items():
                    cam_folder = os.path.join(storage_path, camera_name)
                    
                    # Find newest recording (run in executor to avoid blocking)
                    try:
                        newest = await loop.run_in_executor(None, _get_newest_recording, cam_folder)
                        if newest:
                            # Parse timestamp from filename: CameraName_YYYYMMDD_HHMMSS.mp4
                            parts = newest.replace('.mp4', '').split('_')
                            if len(parts) >= 3:
                                date_str = parts[-2]
                                time_str = parts[-1]
                                try:
                                    last_rec = datetime.datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                                    camera_last_recording[camera_name] = last_rec
                                except ValueError:
                                    pass
                    except Exception as e:
                        log_to_file(f"Watchdog: Error checking {camera_name}: {e}")
                    
                    # Check if any motion sensor is active
                    camera_has_motion = False
                    for motion_entity in motion_entities:
                        state = hass.states.get(motion_entity)
                        if state and state.state == "on":
                            camera_has_motion = True
                            break
                    camera_expected_activity[camera_name] = camera_has_motion
                
                # Log health status
                now_dt = datetime.datetime.now()
                stale_cameras = []
                for cam_name, last_rec in camera_last_recording.items():
                    age_minutes = (now_dt - last_rec).total_seconds() / 60
                    # If camera has motion but no recording in 30+ minutes, flag it
                    if camera_expected_activity.get(cam_name, False) and age_minutes > 30:
                        stale_cameras.append(f"{cam_name} ({age_minutes:.0f}min)")
                
                if stale_cameras:
                    log_to_file(f"⚠️ WATCHDOG: Stale cameras (motion active but old recordings): {', '.join(stale_cameras)}")
                    _LOGGER.warning(f"RTSP Recorder Watchdog: Cameras may have issues: {stale_cameras}")
                    
            except Exception as e:
                log_to_file(f"Watchdog error: {e}")
        
        # Run watchdog every 15 minutes
        unsub_watchdog = async_track_time_interval(hass, check_camera_health, timedelta(minutes=15))
        entry.async_on_unload(unsub_watchdog)
        
        # Run initial check after 60 seconds
        hass.loop.call_later(60, lambda: hass.async_create_task(check_camera_health()))

        # ===== Register WebSocket Handlers (from websocket_handlers.py) =====
        
        register_websocket_handlers(
            hass=hass,
            entry=entry,
            config_data=config_data,
            analysis_output_path=analysis_output_path,
            analysis_detector_url=analysis_detector_url,
            analysis_face_match_threshold=analysis_face_match_threshold,
            analysis_perf_cpu_entity=analysis_perf_cpu_entity,
            analysis_perf_igpu_entity=analysis_perf_igpu_entity,
            analysis_perf_coral_entity=analysis_perf_coral_entity,
        )
        
        register_people_websocket_handlers(
            hass=hass,
            analysis_output_path=analysis_output_path,
            analysis_face_match_threshold=analysis_face_match_threshold,
            validate_person_name_func=_validate_person_name,
        )

        log_to_file("Setup Success.")

    except Exception as e:
        log_to_file(f"CRITICAL SETUP ERROR: {e}\n{traceback.format_exc()}")
        raise e

    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    return True


async def update_listener(hass, entry):
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
