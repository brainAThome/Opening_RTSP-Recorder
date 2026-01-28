"""RTSP Recorder Integration."""
import logging
import os
import traceback
import asyncio
import datetime
import json
from datetime import timedelta
from typing import Any
import voluptuous as vol
import aiohttp
from homeassistant.core import ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components import websocket_api
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.event import async_track_state_change_event
from .retention import cleanup_recordings
from .recorder import async_record_stream, async_take_snapshot
from .analysis import analyze_recording, detect_available_devices

# ===== Inference Stats Tracker =====
import time as _time
from collections import deque as _deque
import threading as _threading

class InferenceStatsTracker:
    """Track inference statistics for performance monitoring."""
    
    def __init__(self, max_history: int = 100):
        self._lock = _threading.Lock()
        self._history = _deque(maxlen=max_history)
        self._total_inferences = 0
        self._coral_inferences = 0
        self._cpu_inferences = 0
        self._last_device = "none"
        self._start_time = _time.time()
    
    def record(self, device: str, duration_ms: float, frame_count: int = 1):
        """Record an inference event."""
        with self._lock:
            now = _time.time()
            self._history.append({
                "timestamp": now,
                "device": device,
                "duration_ms": duration_ms,
                "frame_count": frame_count,
            })
            self._total_inferences += frame_count
            self._last_device = device
            if device == "coral_usb":
                self._coral_inferences += frame_count
            else:
                self._cpu_inferences += frame_count
    
    def get_stats(self) -> dict:
        """Get current statistics."""
        with self._lock:
            now = _time.time()
            uptime = now - self._start_time
            
            # Calculate stats from recent history (last 60 seconds)
            recent = [h for h in self._history if now - h["timestamp"] < 60]
            
            # Inferences per minute
            ipm = len(recent)
            
            # Average inference time
            if recent:
                avg_ms = sum(h["duration_ms"] for h in recent) / len(recent)
                last_ms = recent[-1]["duration_ms"] if recent else 0
            else:
                avg_ms = 0
                last_ms = 0
            
            # Coral usage percentage (of total inferences)
            coral_pct = 0
            if self._total_inferences > 0:
                coral_pct = round(100 * self._coral_inferences / self._total_inferences, 1)
            
            # Recent coral usage (last 60s)
            recent_coral = sum(1 for h in recent if h["device"] == "coral_usb")
            recent_coral_pct = round(100 * recent_coral / len(recent), 1) if recent else 0
            
            return {
                "uptime_seconds": round(uptime, 0),
                "total_inferences": self._total_inferences,
                "coral_inferences": self._coral_inferences,
                "cpu_inferences": self._cpu_inferences,
                "last_device": self._last_device,
                "inferences_per_minute": ipm,
                "avg_inference_ms": round(avg_ms, 1),
                "last_inference_ms": round(last_ms, 1),
                "coral_usage_pct": coral_pct,
                "recent_coral_pct": recent_coral_pct,
            }

_inference_stats = InferenceStatsTracker()

def get_system_stats() -> dict:
    """Read system stats directly from /proc."""
    stats = {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "memory_used_mb": 0,
        "memory_total_mb": 0,
    }
    
    try:
        # CPU usage - read /proc/stat twice with delay
        import time as _t
        
        def read_cpu():
            with open("/proc/stat", "r") as f:
                line = f.readline()
            parts = line.split()
            # user, nice, system, idle, iowait, irq, softirq
            idle = int(parts[4])
            total = sum(int(p) for p in parts[1:8])
            return idle, total
        
        idle1, total1 = read_cpu()
        _t.sleep(0.1)
        idle2, total2 = read_cpu()
        
        idle_delta = idle2 - idle1
        total_delta = total2 - total1
        if total_delta > 0:
            stats["cpu_percent"] = round(100.0 * (1.0 - idle_delta / total_delta), 1)
        
        # Memory from /proc/meminfo
        with open("/proc/meminfo", "r") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    meminfo[key] = int(parts[1])
        
        total_kb = meminfo.get("MemTotal", 0)
        available_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
        used_kb = total_kb - available_kb
        
        stats["memory_total_mb"] = round(total_kb / 1024, 0)
        stats["memory_used_mb"] = round(used_kb / 1024, 0)
        if total_kb > 0:
            stats["memory_percent"] = round(100.0 * used_kb / total_kb, 1)
            
    except Exception as e:
        _LOGGER.warning(f"Failed to read system stats: {e}")
    
    return stats
# ===== End Stats Tracker =====

_LOGGER = logging.getLogger(__name__)

DOMAIN = "rtsp_recorder"

def _parse_hhmm(value: str) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        parts = value.strip().split(":")
        if len(parts) != 2:
            return None
        hour = int(parts[0])
        minute = int(parts[1])
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        return hour, minute
    except Exception:
        return None


def _list_video_files(storage_path: str, camera: str | None = None) -> list[str]:
    if not os.path.exists(storage_path):
        return []
    results = []
    for root, _, files in os.walk(storage_path):
        if "_analysis" in root:
            continue
        if camera and os.path.basename(root) != camera:
            continue
        for fname in files:
            if fname.lower().endswith(".mp4"):
                results.append(os.path.join(root, fname))
    return results


def _read_analysis_results(output_dir: str, limit: int = 50) -> list[dict[str, Any]]:
    if not os.path.exists(output_dir):
        return []
    results = []
    for name in os.listdir(output_dir):
        if not name.startswith("analysis_"):
            continue
        job_dir = os.path.join(output_dir, name)
        result_path = os.path.join(job_dir, "result.json")
        if not os.path.exists(result_path):
            continue
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.pop("frames", None)
            results.append(data)
        except Exception:
            continue
    results.sort(key=lambda r: r.get("created_utc", ""), reverse=True)
    return results[:limit]


def _find_analysis_for_video(output_dir: str, video_path: str) -> dict[str, Any] | None:
    for item in _read_analysis_results(output_dir, limit=200):
        if item.get("video_path") == video_path:
            return item
    return None


def _build_analysis_index(output_dir: str) -> set[str]:
    existing = set()
    for item in _read_analysis_results(output_dir, limit=10000):
        path = item.get("video_path")
        if path:
            existing.add(path)
    return existing


def _summarize_analysis(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    by_device: dict[str, int] = {}
    durations = []
    frames = []
    for item in items:
        device = item.get("device", "unknown")
        by_device[device] = by_device.get(device, 0) + 1
        if isinstance(item.get("duration_sec"), (int, float)):
            durations.append(float(item["duration_sec"]))
        if isinstance(item.get("frame_count"), (int, float)):
            frames.append(int(item["frame_count"]))
    avg_duration = round(sum(durations) / len(durations), 2) if durations else 0
    avg_frames = round(sum(frames) / len(frames), 2) if frames else 0
    return {
        "total": total,
        "by_device": by_device,
        "avg_duration_sec": avg_duration,
        "avg_frame_count": avg_frames,
    }

def log_to_file(msg):
    """Fallback logging to file + Standard Logger."""
    # Write to standard logger for "Enable Debug Logging" support
    _LOGGER.debug(msg)
    
    # Keep file logging for fallback
    try:
        with open("/config/rtsp_debug.log", "a") as f:
            f.write(f"INIT: {msg}\n")
    except Exception:
        pass

async def async_setup(hass, config):
    """Set up the Ring Recorder component."""
    return True

async def async_setup_entry(hass: ConfigEntry, entry: ConfigEntry):
    """Set up RTSP Recorder from a config entry."""
    log_to_file(f"START: Setting up RTSP Recorder entry {entry.entry_id}")
    
    # Merge data and options
    config_data = {**entry.data, **entry.options}
    
    storage_path = config_data.get("storage_path", "/media/rtsp_recordings")
    snapshot_path_base = config_data.get("snapshot_path", "/config/www/thumbnails")
    retention_days = config_data.get("retention_days", 7)
    snapshot_retention_days = config_data.get("snapshot_retention_days", 7)
    retention_hours = config_data.get("retention_hours", 0)
    analysis_enabled = config_data.get("analysis_enabled", True)
    analysis_device = config_data.get("analysis_device", "cpu")
    analysis_objects = config_data.get("analysis_objects", ["person"])
    analysis_output_path = config_data.get("analysis_output_path", os.path.join(storage_path, "_analysis"))
    analysis_frame_interval = int(config_data.get("analysis_frame_interval", 2))
    analysis_detector_url = config_data.get("analysis_detector_url", "")
    analysis_detector_confidence = float(config_data.get("analysis_detector_confidence", 0.4))
    analysis_auto_enabled = config_data.get("analysis_auto_enabled", False)
    analysis_auto_mode = config_data.get("analysis_auto_mode", "daily")
    analysis_auto_time = config_data.get("analysis_auto_time", "03:00")
    analysis_auto_interval_hours = int(config_data.get("analysis_auto_interval_hours", 24))
    analysis_auto_since_days = int(config_data.get("analysis_auto_since_days", 1))
    analysis_auto_limit = int(config_data.get("analysis_auto_limit", 50))
    analysis_auto_skip_existing = bool(config_data.get("analysis_auto_skip_existing", True))
    analysis_perf_cpu_entity = config_data.get("analysis_perf_cpu_entity")
    analysis_perf_igpu_entity = config_data.get("analysis_perf_igpu_entity")
    analysis_perf_coral_entity = config_data.get("analysis_perf_coral_entity")
    
    # Build override map
    # Ignore keys that are known config settings
    known_settings = [
        "storage_path",
        "snapshot_path",
        "retention_days",
        "snapshot_retention_days",
        "retention_hours",
        "camera_filter",
        "analysis_enabled",
        "analysis_device",
        "analysis_objects",
        "analysis_output_path",
        "analysis_frame_interval",
        "analysis_detector_url",
        "analysis_detector_confidence",
        "analysis_auto_enabled",
        "analysis_auto_mode",
        "analysis_auto_time",
        "analysis_auto_interval_hours",
        "analysis_auto_since_days",
        "analysis_auto_limit",
        "analysis_auto_skip_existing",
        "analysis_perf_cpu_entity",
        "analysis_perf_igpu_entity",
        "analysis_perf_coral_entity",
    ]
    
    override_map = {}
    for key, value in config_data.items():
        if key in known_settings:
            continue
            
        # Parse retention_hours_CameraName keys
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
            
        # 2. Define Recording Logic (Reusable)
        async def handle_save_recording(call: ServiceCall = None, camera_name: str = None, duration: int = 30, snapshot_delay: float = 0):
            """
            Handle recording. Can be called via Service (manual) or Internal Event (auto).
            """
            try:
                entity_id = None
                
                # Case A: Service Call
                if call:
                    log_to_file("Service save_recording called!")
                    entity_id = call.data.get("entity_id")
                    if not entity_id:
                        _LOGGER.error("No entity_id provided")
                        return
                    
                    # Resolve Camera Name from Entity
                    state = hass.states.get(entity_id)
                    if not state:
                        _LOGGER.error(f"Entity {entity_id} not found")
                        return
                    friendly_name = state.attributes.get("friendly_name", entity_id)
                    
                    # Sanitize
                    clean_name_raw = friendly_name.replace("🎥", "").strip().replace(" ", "_")
                    clean_name = clean_name_raw
                    
                    # Override params if provided in call
                    duration = call.data.get("duration", duration)
                    snapshot_delay = call.data.get("snapshot_delay", snapshot_delay)

                # Case B: Internal Call
                elif camera_name:
                    log_to_file(f"Internal Motion Trigger for: {camera_name}")
                    clean_name_raw = camera_name
                    clean_name = clean_name_raw
                    # Find matching entity for recording service (if needed)
                    found_entity = None
                    for state in hass.states.async_all("camera"):
                        fn = state.attributes.get("friendly_name", "").replace("🎥", "").strip().replace(" ", "_")
                        if fn == clean_name or clean_name in state.entity_id:
                            found_entity = state.entity_id
                            break
                    if found_entity:
                        entity_id = found_entity

                else:
                    return # No context

                # Sanitize Chars
                for char in [":", "/", "\\", "?", "*", "\"", "<", ">", "|"]:
                    clean_name = clean_name.replace(char, "")

                if not clean_name:
                    clean_name = "unknown"

                # Resolve optional RTSP URL override (support legacy key if present)
                rtsp_key = f"rtsp_url_{clean_name}"
                legacy_rtsp_key = f"rtsp_url_{clean_name_raw}"
                rtsp_url = config_data.get(rtsp_key, "")
                if not rtsp_url and legacy_rtsp_key != rtsp_key:
                    rtsp_url = config_data.get(legacy_rtsp_key, "")
                use_rtsp = isinstance(rtsp_url, str) and rtsp_url.strip()
                if use_rtsp:
                    rtsp_url = rtsp_url.strip()

                # If no entity found and no RTSP URL, abort
                if not entity_id and not use_rtsp:
                    log_to_file(f"ERROR: Could not find Camera Entity or RTSP URL for {clean_name}")
                    return

                # clean_name is already sanitized

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
                
            except Exception as e:
                log_to_file(f"Error in save_recording: {e}")
                _LOGGER.error(f"Error in save_recording: {e}")

        hass.services.async_register(DOMAIN, "save_recording", handle_save_recording)

        def _sensor_snapshot() -> dict[str, Any]:
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
                "ts": datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
            }

        async def _analyze_batch(
            *,
            device: str,
            objects: list[str],
            since_days: int | None = None,
            limit: int | None = None,
            skip_existing: bool = True,
            camera: str | None = None,
        ) -> int:
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

            processed = 0
            for path in files:
                try:
                    perf_snapshot = _sensor_snapshot()
                    await analyze_recording(
                        video_path=path,
                        output_root=analysis_output_path,
                        objects=objects,
                        device=device,
                        interval_s=analysis_frame_interval,
                        perf_snapshot=perf_snapshot,
                        detector_url=analysis_detector_url,
                        detector_confidence=analysis_detector_confidence,
                    )
                    processed += 1
                except Exception as e:
                    log_to_file(f"Batch analysis error for {path}: {e}")
                await asyncio.sleep(0)

            return processed

        # Offline Analysis Service
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
                perf_snapshot = _sensor_snapshot()
                result = await analyze_recording(
                    video_path=video_path,
                    output_root=output_dir,
                    objects=objects,
                    device=device,
                    interval_s=analysis_frame_interval,
                    perf_snapshot=perf_snapshot,
                    detector_url=analysis_detector_url,
                    detector_confidence=analysis_detector_confidence,
                )
                log_to_file(f"Analysis completed: {result.get('status')} -> {output_dir}")
            except Exception as e:
                log_to_file(f"Error analyzing recording: {e}")
                _LOGGER.error(f"Error analyzing recording: {e}")

        hass.services.async_register(DOMAIN, "analyze_recording", handle_analyze_recording)

        # Analyze All Recordings Service
        async def handle_analyze_all_recordings(call: ServiceCall):
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
        
        # Delete Recording Service
        async def handle_delete_recording(call: ServiceCall):
            """Delete a recording and its thumbnail."""
            media_id = call.data.get("media_id", "")
            log_to_file(f"Delete recording requested: {media_id}")
            
            try:
                # media_id format: media-source://media_source/local/rtsp_recordings/Camera/file.mp4
                # Extract path from media_id
                if "local/" in media_id:
                    relative_path = media_id.split("local/", 1)[1]
                    video_path = f"/media/{relative_path}"
                else:
                    log_to_file(f"Unknown media_id format: {media_id}")
                    return
                
                # Delete video
                if os.path.exists(video_path):
                    os.remove(video_path)
                    log_to_file(f"Deleted video: {video_path}")
                else:
                    log_to_file(f"Video not found: {video_path}")
                
                # Delete thumbnail
                # Video: /media/rtsp_recordings/Camera/Camera_20260127_121500.mp4
                # Thumb: <snapshot_path_base>/Camera/Camera_20260127_121500.jpg
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
                _LOGGER.error(f"Error deleting recording: {e}")
                raise

        hass.services.async_register(DOMAIN, "delete_recording", handle_delete_recording)
        
        # 3. Register Motion Listeners (Auto-Record)
        
        # Helper to create proper closure
        def _create_motion_handler(cam_name, record_duration, snap_delay):
            async def _motion_changed(event):
                new_state = event.data.get("new_state")
                if new_state and new_state.state == "on":
                    log_to_file(f"Motion detected on {event.data['entity_id']} -> Triggering {cam_name}")
                    await handle_save_recording(camera_name=cam_name, duration=record_duration, snapshot_delay=snap_delay)
            return _motion_changed

        for key, value in config_data.items():
            try:
                if key.startswith("sensor_"):
                    # Key format: sensor_CameraName (underscored)
                    # Value: binary_sensor.entity_id
                    camera_target = key.replace("sensor_", "")
                    motion_entity = value
                    
                    # Get Configured Duration (default 120s)
                    duration_key = f"duration_{camera_target}"
                    record_duration = config_data.get(duration_key, 120)
                    
                    # Get Snapshot Delay (default 0)
                    delay_key = f"snapshot_delay_{camera_target}"
                    snap_delay = config_data.get(delay_key, 0)
                    
                    log_to_file(f"Setup Auto-Record: {motion_entity} -> {camera_target} ({record_duration}s, delay {snap_delay}s)")
                    
                    async_track_state_change_event(
                        hass, 
                        [motion_entity], 
                        _create_motion_handler(camera_target, record_duration, snap_delay)
                    )
            except Exception as e:
                log_to_file(f"Error setting up auto-record for {key}: {e}")
                _LOGGER.error(f"Error setting up auto-record: {e}")

        # 4. Schedule Retention Cleanup
        async def run_cleanup(now=None):
            log_to_file("Running scheduled retention cleanup...")
            
            # 1. Video Cleanup
            await hass.async_add_executor_job(
                cleanup_recordings, 
                storage_path, 
                retention_days, 
                retention_hours,
                override_map
            )
            
            # 2. Snapshot Cleanup
            snapshot_path = snapshot_path_base
            await hass.async_add_executor_job(
                cleanup_recordings, 
                snapshot_path, 
                snapshot_retention_days, 
                0, # Global hours for snapshots usually 0
                override_map # Same overrides apply to snapshots (by folder name)
            )

        # Run once on startup (after 30s delay)
        hass.loop.call_later(30, lambda: hass.async_create_task(run_cleanup()))
        
        # Run daily at same time
        async_track_time_interval(hass, run_cleanup, timedelta(hours=24))

        # Auto Analysis Scheduler
        async def run_auto_analysis(now=None):
            if not analysis_enabled or not analysis_auto_enabled:
                return
            try:
                processed = await _analyze_batch(
                    device=analysis_device,
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
                async_track_time_interval(hass, run_auto_analysis, timedelta(hours=interval_hours))
            else:
                hhmm = _parse_hhmm(analysis_auto_time) or (3, 0)
                async_track_time_change(hass, run_auto_analysis, hour=hhmm[0], minute=hhmm[1], second=0)
        
        # Register update listener
        entry.async_on_unload(entry.add_update_listener(update_listener))

        # Websocket API: Analysis overview
        def _sensor_info(entity_id: str | None) -> dict[str, Any] | None:
            if not entity_id:
                return None
            state = hass.states.get(entity_id)
            if not state:
                return {"entity_id": entity_id, "state": None, "unit": None, "name": None}
            return {
                "entity_id": entity_id,
                "state": state.state,
                "unit": state.attributes.get("unit_of_measurement"),
                "name": state.attributes.get("friendly_name", entity_id),
            }

        async def _fetch_remote_devices(url: str) -> list[str]:
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

        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/get_analysis_overview",
                vol.Optional("limit", default=20): int,
            }
        )
        @websocket_api.async_response
        async def ws_get_analysis_overview(hass, connection, msg):
            limit = msg.get("limit", 20)
            items = await hass.async_add_executor_job(_read_analysis_results, analysis_output_path, limit)
            stats = _summarize_analysis(items)
            devices = []
            if analysis_detector_url:
                devices = await _fetch_remote_devices(analysis_detector_url)
            if not devices:
                devices = await hass.async_add_executor_job(detect_available_devices)
            perf = {
                "cpu": _sensor_info(analysis_perf_cpu_entity),
                "igpu": _sensor_info(analysis_perf_igpu_entity),
                "coral": _sensor_info(analysis_perf_coral_entity),
            }
            connection.send_result(msg["id"], {"items": items, "stats": stats, "perf": perf, "devices": devices})

        websocket_api.async_register_command(hass, ws_get_analysis_overview)

        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/get_analysis_result",
                vol.Required("media_id"): str,
            }
        )
        @websocket_api.async_response
        async def ws_get_analysis_result(hass, connection, msg):
            media_id = msg.get("media_id", "")
            if "local/" not in media_id:
                connection.send_result(msg["id"], {})
                return
            relative_path = media_id.split("local/", 1)[1]
            video_path = f"/media/{relative_path}"
            result = await hass.async_add_executor_job(_find_analysis_for_video, analysis_output_path, video_path)
            if result:
                result.pop("frames", None)
            connection.send_result(msg["id"], result or {})

        websocket_api.async_register_command(hass, ws_get_analysis_result)

        # ===== Detector Stats endpoint =====
        async def _fetch_detector_stats(url: str) -> dict[str, Any]:
            """Fetch stats from detector service."""
            if not url:
                return {"error": "no_detector_url"}
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{url.rstrip('/')}/stats", timeout=5) as resp:
                        if resp.status == 404:
                            # Stats endpoint not available, return basic info
                            async with session.get(f"{url.rstrip('/')}/info", timeout=5) as info_resp:
                                if info_resp.status == 200:
                                    info = await info_resp.json()
                                    return {
                                        "available": True,
                                        "devices": info.get("devices", []),
                                        "stats_supported": False,
                                    }
                            return {"available": False, "error": "stats_not_supported"}
                        if resp.status != 200:
                            return {"available": False, "error": f"http_{resp.status}"}
                        data = await resp.json()
                        data["available"] = True
                        data["stats_supported"] = True
                        return data
            except asyncio.TimeoutError:
                return {"available": False, "error": "timeout"}
            except Exception as e:
                return {"available": False, "error": str(e)}

        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/get_detector_stats",
            }
        )
        @websocket_api.async_response
        async def ws_get_detector_stats(hass, connection, msg):
            """Return detector stats including CPU, Coral status, inference times."""
            stats = await _fetch_detector_stats(analysis_detector_url)
            
            # Add perf sensor values
            perf = {
                "cpu": _sensor_info(analysis_perf_cpu_entity),
                "igpu": _sensor_info(analysis_perf_igpu_entity),
                "coral": _sensor_info(analysis_perf_coral_entity),
            }
            stats["perf_sensors"] = perf
            
            # Add inference tracking stats
            stats["inference_stats"] = _inference_stats.get_stats()
            
            # Add live system stats from /proc
            stats["system_stats"] = await hass.async_add_executor_job(get_system_stats)
            
            connection.send_result(msg["id"], stats)

        websocket_api.async_register_command(hass, ws_get_detector_stats)

        # WebSocket: Test inference (triggers a single detection to populate stats)
        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/test_inference",
            }
        )
        @websocket_api.async_response
        async def ws_test_inference(hass, connection, msg):
            """Run a single test inference to populate Coral statistics."""
            import aiohttp
            import time as _t
            import io
            result = {"success": False, "message": "Unknown error", "device": None, "duration_ms": 0}
            
            if not analysis_detector_url:
                result["message"] = "Detector URL not configured"
                connection.send_result(msg["id"], result)
                return
            
            try:
                # Create a valid JPEG test image using PIL
                try:
                    from PIL import Image
                    img = Image.new('RGB', (320, 240), color=(128, 128, 128))
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=70)
                    test_image = buf.getvalue()
                except ImportError:
                    # Fallback: minimal valid 1x1 JPEG (base64 decoded)
                    import base64
                    # This is a valid 1x1 gray JPEG
                    test_image = base64.b64decode(
                        '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof'
                        'Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh'
                        'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAAR'
                        'CAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAA'
                        'AAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMB'
                        'AAIRAxEAPwCwAB//2Q=='
                    )
                
                async with aiohttp.ClientSession() as session:
                    form = aiohttp.FormData()
                    form.add_field("file", test_image, filename="test.jpg", content_type="image/jpeg")
                    form.add_field("confidence", "0.1")
                    form.add_field("device", "coral_usb")  # Request Coral explicitly
                    
                    start = _t.time()
                    async with session.post(f"{analysis_detector_url.rstrip('/')}/detect", data=form, timeout=30) as resp:
                        duration_ms = (_t.time() - start) * 1000
                        if resp.status == 200:
                            data = await resp.json()
                            used_device = data.get("device", "cpu")
                            _inference_stats.record(used_device, duration_ms, 1)
                            result = {
                                "success": True,
                                "message": f"Test inference completed on {used_device}",
                                "device": used_device,
                                "duration_ms": round(duration_ms, 1),
                                "detections": len(data.get("detections", []))
                            }
                        else:
                            body = await resp.text()
                            result["message"] = f"Detector returned status {resp.status}: {body[:100]}"
            except Exception as e:
                import traceback
                result["message"] = f"{str(e)}"
                log_to_file(f"Test inference error: {traceback.format_exc()}")
            
            connection.send_result(msg["id"], result)

        websocket_api.async_register_command(hass, ws_test_inference)

        # WebSocket API: Get Analysis Config
        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/get_analysis_config",
            }
        )
        @websocket_api.async_response
        async def ws_get_analysis_config(hass, connection, msg):
            """Return current analysis schedule configuration."""
            result = {
                "analysis_enabled": analysis_enabled,
                "analysis_auto_enabled": analysis_auto_enabled,
                "analysis_auto_mode": analysis_auto_mode,
                "analysis_auto_time": analysis_auto_time,
                "analysis_auto_interval_hours": analysis_auto_interval_hours,
                "analysis_auto_since_days": analysis_auto_since_days,
                "analysis_auto_limit": analysis_auto_limit,
                "analysis_auto_skip_existing": analysis_auto_skip_existing,
                "analysis_device": analysis_device,
                "analysis_objects": analysis_objects,
            }
            connection.send_result(msg["id"], result)

        websocket_api.async_register_command(hass, ws_get_analysis_config)

        # WebSocket API: Set Analysis Config (updates config entry)
        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/set_analysis_config",
                vol.Optional("analysis_auto_enabled"): bool,
                vol.Optional("analysis_auto_mode"): str,
                vol.Optional("analysis_auto_time"): str,
                vol.Optional("analysis_auto_interval_hours"): int,
                vol.Optional("analysis_auto_since_days"): int,
                vol.Optional("analysis_auto_limit"): int,
                vol.Optional("analysis_auto_skip_existing"): bool,
            }
        )
        @websocket_api.async_response
        async def ws_set_analysis_config(hass, connection, msg):
            """Update analysis schedule configuration."""
            try:
                # Update only provided fields
                updatable_fields = [
                    "analysis_auto_enabled",
                    "analysis_auto_mode", 
                    "analysis_auto_time",
                    "analysis_auto_interval_hours",
                    "analysis_auto_since_days",
                    "analysis_auto_limit",
                    "analysis_auto_skip_existing",
                ]
                
                # Build updates dict
                updates = {}
                for field in updatable_fields:
                    if field in msg:
                        updates[field] = msg[field]
                
                # Update both data AND options (HA uses options when options_flow exists)
                new_data = dict(entry.data)
                new_options = dict(entry.options) if entry.options else {}
                
                new_data.update(updates)
                new_options.update(updates)
                
                # Update config entry with both
                hass.config_entries.async_update_entry(entry, data=new_data, options=new_options)
                
                connection.send_result(msg["id"], {
                    "success": True,
                    "message": "Config updated. Reload integration for scheduler changes to take effect.",
                    "updated": updates
                })
            except Exception as e:
                log_to_file(f"Set analysis config error: {e}")
                connection.send_result(msg["id"], {
                    "success": False,
                    "message": str(e)
                })

        websocket_api.async_register_command(hass, ws_set_analysis_config)

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
