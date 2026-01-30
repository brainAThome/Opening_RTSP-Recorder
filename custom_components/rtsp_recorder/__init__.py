"""RTSP Recorder Integration."""
import logging
import os
import re
import traceback
import asyncio
import datetime
import json
import uuid
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

import sys as _sys

# ===== Platform Detection (MED-001 Fix) =====
IS_LINUX = _sys.platform.startswith('linux')

def _get_system_stats_sync() -> dict:
    """Read system stats (Linux: /proc, other platforms: defaults)."""
    import time as _t
    
    stats = {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "memory_used_mb": 0,
        "memory_total_mb": 0,
    }
    
    # MED-001 Fix: Only access /proc on Linux
    if not IS_LINUX:
        return stats
    
    try:
        # CPU usage - read /proc/stat twice with delay
        def read_cpu():
            with open("/proc/stat", "r") as f:
                line = f.readline()
            parts = line.split()
            # user, nice, system, idle, iowait, irq, softirq
            idle = int(parts[4])
            total = sum(int(p) for p in parts[1:8])
            return idle, total
        
        idle1, total1 = read_cpu()
        _t.sleep(0.1)  # Safe: runs in executor thread, not event loop
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
            
    except Exception:
        pass  # Return default stats on error
    
    return stats


def get_system_stats() -> dict:
    """Get system stats (wrapper for sync contexts)."""
    return _get_system_stats_sync()
# ===== End Stats Tracker =====

_LOGGER = logging.getLogger(__name__)

DOMAIN = "rtsp_recorder"

PEOPLE_DB_VERSION = 1
PEOPLE_DB_DEFAULT_PATH = "/config/rtsp_recorder_people.json"
_people_lock = asyncio.Lock()

# ===== Rate Limiting (MED-004 Fix) =====
# Semaphore to limit concurrent analysis operations
MAX_CONCURRENT_ANALYSES = 2
_analysis_semaphore: asyncio.Semaphore | None = None


def _get_analysis_semaphore() -> asyncio.Semaphore:
    """Get or create the analysis semaphore."""
    global _analysis_semaphore
    if _analysis_semaphore is None:
        _analysis_semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANALYSES)
    return _analysis_semaphore
# ===== End Rate Limiting =====


# ===== Path Validation (HIGH-001 Fix) =====
def _validate_media_path(media_id: str, allowed_base: str = "/media/rtsp_recordings") -> str | None:
    """Validate media_id and return safe path, or None if invalid.
    
    Prevents path traversal attacks by ensuring the resolved path
    stays within the allowed base directory.
    """
    if not media_id:
        return None
    
    try:
        # Extract relative path from media_id
        if "local/" in media_id:
            relative_path = media_id.split("local/", 1)[1]
        else:
            return None
        
        # Construct and resolve the full path
        video_path = os.path.join("/media", relative_path)
        resolved_path = os.path.realpath(video_path)
        
        # Security check: ensure path is within allowed directory
        if not resolved_path.startswith(allowed_base):
            _LOGGER.warning(f"Path traversal attempt blocked: {media_id} -> {resolved_path}")
            return None
        
        # Additional checks for dangerous patterns
        if ".." in relative_path or relative_path.startswith("/"):
            _LOGGER.warning(f"Suspicious path pattern blocked: {media_id}")
            return None
        
        return resolved_path
    except Exception as e:
        _LOGGER.error(f"Path validation error: {e}")
        return None
# ===== End Path Validation =====


# ===== Input Validation Constants (MED-002 Fix) =====
MAX_PERSON_NAME_LENGTH = 100
VALID_NAME_PATTERN = re.compile(r'^[\w\s\-\.äöüÄÖÜß]+$')  # Allow letters, numbers, spaces, hyphens, dots, German umlauts


def _validate_person_name(name: str) -> tuple[bool, str]:
    """Validate person name for length and allowed characters.
    
    Returns (is_valid, error_message).
    """
    if not name:
        return False, "Name darf nicht leer sein"
    if len(name) > MAX_PERSON_NAME_LENGTH:
        return False, f"Name zu lang (max {MAX_PERSON_NAME_LENGTH} Zeichen)"
    if not VALID_NAME_PATTERN.match(name):
        return False, "Name enthält ungültige Zeichen"
    return True, ""
# ===== End Input Validation =====


def _compute_centroid(embeddings: list) -> list[float] | None:
    """Compute the centroid (average) of multiple embeddings.
    
    This creates a single representative vector for a person,
    making face matching faster and more robust.
    """
    if not embeddings:
        return None
    
    vectors = []
    for emb in embeddings:
        if isinstance(emb, dict):
            emb = emb.get("vector", [])
        if isinstance(emb, list) and len(emb) > 0:
            try:
                vec = [float(x) for x in emb]
                vectors.append(vec)
            except (TypeError, ValueError):
                continue
    
    if not vectors:
        return None
    
    # All vectors should have the same dimension
    dim = len(vectors[0])
    centroid = [0.0] * dim
    
    for vec in vectors:
        if len(vec) != dim:
            continue
        for i in range(dim):
            centroid[i] += vec[i]
    
    n = len(vectors)
    if n == 0:
        return None
    centroid = [c / n for c in centroid]
    
    # Normalize the centroid for cosine similarity
    norm = sum(c * c for c in centroid) ** 0.5
    if norm > 0:
        centroid = [c / norm for c in centroid]
    
    return centroid


def _update_person_centroid(person: dict) -> dict:
    """Update the centroid for a single person based on their embeddings."""
    embeddings = person.get("embeddings", [])
    if embeddings:
        centroid = _compute_centroid(embeddings)
        if centroid:
            person["centroid"] = centroid
    return person


def _update_all_centroids(data: dict) -> dict:
    """Update centroids for all people in the database."""
    for person in data.get("people", []):
        _update_person_centroid(person)
    return data


def _default_people_db() -> dict[str, Any]:
    # MED-005 Fix: Use timezone-aware datetime instead of deprecated utcnow()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    return {
        "version": PEOPLE_DB_VERSION,
        "people": [],
        "created_utc": now_utc.strftime("%Y%m%d_%H%M%S"),
        "updated_utc": now_utc.strftime("%Y%m%d_%H%M%S"),
    }


async def _load_people_db(path: str) -> dict[str, Any]:
    async with _people_lock:
        if not os.path.exists(path):
            data = _default_people_db()
            def _write():
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            await asyncio.to_thread(_write)
            return data
        try:
            def _read():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            data = await asyncio.to_thread(_read)
            if not isinstance(data, dict):
                return _default_people_db()
            if "people" not in data:
                data["people"] = []
            
            # Ensure centroids are computed for all people
            needs_save = False
            for person in data.get("people", []):
                if "centroid" not in person and person.get("embeddings"):
                    _update_person_centroid(person)
                    needs_save = True
            
            # Save updated centroids if any were computed
            if needs_save:
                data["updated_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
                def _write_updated():
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                await asyncio.to_thread(_write_updated)
            
            return data
        except Exception:
            return _default_people_db()


async def _save_people_db(path: str, data: dict[str, Any]) -> None:
    async with _people_lock:
        # MED-005 Fix: Use timezone-aware datetime
        data["updated_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        def _write():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        await asyncio.to_thread(_write)


# ===== Atomic People DB Update (HIGH-002 Fix) =====
async def _update_people_db(path: str, update_fn) -> dict[str, Any]:
    """Atomically update People DB with a modifier function.
    
    Ensures the entire read-modify-write cycle is protected by a single lock
    to prevent race conditions between concurrent updates.
    
    Args:
        path: Path to people DB JSON file
        update_fn: Function that takes the current data dict and returns modified data
    
    Returns:
        The updated data dict
    """
    async with _people_lock:
        # Read current data
        if not os.path.exists(path):
            data = _default_people_db()
        else:
            try:
                def _read():
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                data = await asyncio.to_thread(_read)
                if not isinstance(data, dict):
                    data = _default_people_db()
                if "people" not in data:
                    data["people"] = []
            except Exception:
                data = _default_people_db()
        
        # Apply update function
        data = update_fn(data)
        
        # Save updated data (MED-005 Fix: timezone-aware)
        data["updated_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        def _write():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        await asyncio.to_thread(_write)
        
        return data
# ===== End Atomic People DB Update =====


def _public_people_view(people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for p in people:
        thumbs = []
        try:
            for emb in (p.get("embeddings") or [])[-5:]:
                if isinstance(emb, dict):
                    t = emb.get("thumb")
                    if t:
                        thumbs.append(t)
        except Exception:
            thumbs = []
        out.append({
            "id": str(p.get("id")) if p.get("id") is not None else None,
            "name": p.get("name"),
            "created_utc": p.get("created_utc"),
            "embeddings_count": len(p.get("embeddings", []) or []),
            "recent_thumbs": thumbs,
        })
    return out


def _normalize_embedding_simple(values: list[float]) -> list[float]:
    if not values:
        return []
    norm = sum((v * v) for v in values) ** 0.5
    if norm == 0:
        return values
    return [v / norm for v in values]

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


def _cosine_similarity_simple(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two embedding vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _match_face_simple(
    embedding: list[float], 
    people: list[dict[str, Any]], 
    threshold: float = 0.6
) -> dict[str, Any] | None:
    """Match a face embedding against the people database."""
    if not embedding or not people:
        return None
    best = None
    best_score = -1.0
    for person in people:
        p_id = person.get("id")
        p_name = person.get("name")
        for emb in person.get("embeddings", []) or []:
            if isinstance(emb, dict):
                emb_vec = emb.get("vector", [])
            else:
                emb_vec = emb
            if not emb_vec or not isinstance(emb_vec, list):
                continue
            try:
                emb_list = [float(v) for v in emb_vec]
            except (TypeError, ValueError):
                continue
            score = _cosine_similarity_simple(embedding, emb_list)
            if score > best_score:
                best_score = score
                best = {"person_id": p_id, "name": p_name, "similarity": round(float(score), 4)}
    if best and best_score >= float(threshold):
        return best
    return None


async def _update_all_face_matches(
    output_dir: str, 
    people: list[dict[str, Any]], 
    threshold: float = 0.6
) -> int:
    """Re-match all faces in existing analysis results against updated people database.
    
    Returns the number of updated result files.
    """
    if not os.path.exists(output_dir):
        return 0
    
    updated_count = 0
    
    def _process_analyses():
        nonlocal updated_count
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
                
                modified = False
                detections = data.get("detections", [])
                
                for detection in detections:
                    faces = detection.get("faces", [])
                    for face in faces:
                        embedding = face.get("embedding")
                        if not embedding or not isinstance(embedding, list):
                            continue
                        try:
                            emb_list = [float(v) for v in embedding]
                        except (TypeError, ValueError):
                            continue
                        
                        # Re-match this face
                        new_match = _match_face_simple(emb_list, people, threshold)
                        old_match = face.get("match")
                        
                        # Update if match changed
                        if new_match != old_match:
                            if new_match:
                                face["match"] = new_match
                            elif "match" in face:
                                del face["match"]
                            modified = True
                
                if modified:
                    with open(result_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    updated_count += 1
                    
            except Exception:
                continue
        
        return updated_count
    
    await asyncio.to_thread(_process_analyses)
    return updated_count


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

def log_to_file(msg: str) -> None:
    """Log message to both standard logger and fallback debug file.
    
    This dual logging approach ensures messages are captured by Home
    Assistant's debug logging system while also maintaining a persistent
    file log for troubleshooting deployment issues.
    
    Args:
        msg: Message to log
    
    Note:
        File logging is async-safe and will use asyncio.to_thread
        when called from an async context.
    """
    # Write to standard logger for "Enable Debug Logging" support
    _LOGGER.debug(msg)
    
    # Keep file logging for fallback
    try:
        def _write_log():
            with open("/config/rtsp_debug.log", "a") as f:
                f.write(f"INIT: {msg}\n")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(_write_log))
        except RuntimeError:
            _write_log()
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
    analysis_face_enabled = bool(config_data.get("analysis_face_enabled", False))
    analysis_face_confidence = float(config_data.get("analysis_face_confidence", 0.2))
    analysis_face_match_threshold = float(config_data.get("analysis_face_match_threshold", 0.35))
    analysis_face_store_embeddings = bool(config_data.get("analysis_face_store_embeddings", True))
    people_db_path = config_data.get("people_db_path", PEOPLE_DB_DEFAULT_PATH)
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
        "analysis_face_enabled",
        "analysis_face_confidence",
        "analysis_face_match_threshold",
        "analysis_face_store_embeddings",
        "people_db_path",
        "analysis_auto_enabled",
        "analysis_auto_mode",
        "analysis_auto_time",
        "analysis_auto_interval_hours",
        "analysis_auto_since_days",
        "analysis_auto_limit",
        "analysis_auto_skip_existing",
        "analysis_auto_new",
        "analysis_auto_force_coral",
        "person_entities_enabled",
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

        # People DB sicherstellen
        await _load_people_db(people_db_path)
            
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
                    clean_name_raw = re.sub(r"[^\w\s-]", "", friendly_name).strip().replace(" ", "_")
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
                        fn = re.sub(r"[^\w\s-]", "", state.attributes.get("friendly_name", "")).strip().replace(" ", "_")
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

                # 3. Auto-Analyze after recording (if "Automatisch neue Videos analysieren" is enabled)
                if analysis_enabled and analysis_auto_new:
                    async def _auto_analyze_when_ready(path: str, cam_name: str, rec_duration: int):
                        try:
                            # Wait for recording to finish (duration + small buffer)
                            await asyncio.sleep(rec_duration + 2)

                            ready = await _wait_for_file_ready(path, max_wait_s=120, stable_checks=3, interval_s=3)
                            if not ready:
                                log_to_file(f"Recording not ready for auto-analysis (timeout): {path}")
                                return

                            log_to_file(f"Auto-analyzing new recording: {path}")
                            perf_snapshot = _sensor_snapshot()

                            # v1.0.6: Use camera-specific objects if configured
                            cam_objects_key = f"analysis_objects_{cam_name}"
                            cam_specific_objects = config_data.get(cam_objects_key, [])
                            objects_to_use = cam_specific_objects if cam_specific_objects else analysis_objects

                            people_data = await _load_people_db(people_db_path)
                            people = people_data.get("people", [])
                            auto_device = await _resolve_auto_device()
                            result = await analyze_recording(
                                video_path=path,
                                output_root=analysis_output_path,
                                objects=objects_to_use,
                                device=auto_device,
                                interval_s=analysis_frame_interval,
                                perf_snapshot=perf_snapshot,
                                detector_url=analysis_detector_url,
                                detector_confidence=analysis_detector_confidence,
                                face_enabled=analysis_face_enabled,
                                face_confidence=analysis_face_confidence,
                                face_match_threshold=analysis_face_match_threshold,
                                face_store_embeddings=analysis_face_store_embeddings,
                                people_db=people,
                                face_detector_url=analysis_detector_url,
                            )
                            if person_entities_enabled:
                                try:
                                    updated = _update_person_entities_from_result(result or {})
                                    if not updated:
                                        _update_person_entities_for_video(path)
                                except Exception:
                                    pass
                            log_to_file(f"Auto-analysis completed for: {path}")
                        except Exception as ae:
                            log_to_file(f"Auto-analysis error: {ae}")

                    hass.async_create_task(_auto_analyze_when_ready(full_path, clean_name, int(duration or 0)))
                
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
                "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S"),
            }

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

            people_data = await _load_people_db(people_db_path)
            people = people_data.get("people", [])

            # MED-004 Fix: Use semaphore for rate limiting
            semaphore = _get_analysis_semaphore()
            
            processed = 0
            for path in files:
                async with semaphore:  # Limit concurrent analyses
                    try:
                        perf_snapshot = _sensor_snapshot()
                        result = await analyze_recording(
                            video_path=path,
                            output_root=analysis_output_path,
                            objects=objects,
                            device=device,
                            interval_s=analysis_frame_interval,
                            perf_snapshot=perf_snapshot,
                            detector_url=analysis_detector_url,
                            detector_confidence=analysis_detector_confidence,
                            face_enabled=analysis_face_enabled,
                            face_confidence=analysis_face_confidence,
                            face_match_threshold=analysis_face_match_threshold,
                            face_store_embeddings=analysis_face_store_embeddings,
                            people_db=people,
                            face_detector_url=analysis_detector_url,
                        )
                        if person_entities_enabled and result:
                            updated = _update_person_entities_from_result(result)
                            if not updated:
                                _update_person_entities_for_video(result.get("video_path"))
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

                async def _run_analysis():
                    try:
                        perf_snapshot = _sensor_snapshot()
                        people_data = await _load_people_db(people_db_path)
                        people = people_data.get("people", [])
                        result = await analyze_recording(
                            video_path=video_path,
                            output_root=output_dir,
                            objects=objects,
                            device=device,
                            interval_s=analysis_frame_interval,
                            perf_snapshot=perf_snapshot,
                            detector_url=analysis_detector_url,
                            detector_confidence=analysis_detector_confidence,
                            face_enabled=analysis_face_enabled,
                            face_confidence=analysis_face_confidence,
                            face_match_threshold=analysis_face_match_threshold,
                            face_store_embeddings=analysis_face_store_embeddings,
                            people_db=people,
                            face_detector_url=analysis_detector_url,
                        )
                        if person_entities_enabled and result:
                            updated = _update_person_entities_from_result(result)
                            if not updated:
                                _update_person_entities_for_video(result.get("video_path"))
                        log_to_file(f"Analysis completed: {result.get('status')} -> {output_dir}")
                    except Exception as e:
                        log_to_file(f"Error analyzing recording: {e}")
                        _LOGGER.error(f"Error analyzing recording: {e}")

                hass.async_create_task(_run_analysis())
                log_to_file(f"Analysis queued: {video_path}")
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
                # Validate media_id and get safe path (HIGH-001 Fix)
                video_path = _validate_media_path(media_id)
                if not video_path:
                    log_to_file(f"Invalid or unsafe media_id rejected: {media_id}")
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
        
        # Delete All Recordings Service (Bulk Delete)
        async def handle_delete_all_recordings(call: ServiceCall):
            """Delete all recordings, optionally filtered by camera and/or age."""
            camera = call.data.get("camera")  # Optional: specific camera folder
            older_than_days = call.data.get("older_than_days", 0)  # 0 = delete all
            include_analysis = call.data.get("include_analysis", False)  # Also delete analysis results
            confirm = call.data.get("confirm", False)  # Safety confirmation
            
            if not confirm:
                log_to_file("Delete all recordings: Missing confirmation flag")
                raise HomeAssistantError("Sicherheitsabfrage: Setze 'confirm: true' um zu bestätigen")
            
            log_to_file(f"Delete all recordings: camera={camera}, older_than_days={older_than_days}, include_analysis={include_analysis}")
            
            deleted_videos = 0
            deleted_thumbs = 0
            deleted_analysis = 0
            errors = []
            
            try:
                import glob
                from datetime import datetime, timedelta
                
                cutoff_date = None
                if older_than_days > 0:
                    cutoff_date = datetime.now() - timedelta(days=older_than_days)
                
                # Find video files
                if camera:
                    # Specific camera folder
                    safe_camera = camera.replace("..", "").replace("/", "_")
                    video_pattern = os.path.join(storage_path, safe_camera, "*.mp4")
                else:
                    # All cameras
                    video_pattern = os.path.join(storage_path, "*", "*.mp4")
                
                video_files = glob.glob(video_pattern)
                
                for video_path in video_files:
                    try:
                        # Skip if not matching age filter
                        if cutoff_date:
                            # Parse date from filename (e.g., Camera_20260130_121500.mp4)
                            filename = os.path.basename(video_path)
                            match = re.search(r'(\d{8})_(\d{6})', filename)
                            if match:
                                date_str = match.group(1)
                                file_date = datetime.strptime(date_str, "%Y%m%d")
                                if file_date >= cutoff_date:
                                    continue  # Skip newer files
                        
                        # Delete video
                        os.remove(video_path)
                        deleted_videos += 1
                        
                        # Delete corresponding thumbnail
                        filename = os.path.basename(video_path).replace('.mp4', '.jpg')
                        cam_folder = os.path.basename(os.path.dirname(video_path))
                        thumb_path = os.path.join(snapshot_path_base, cam_folder, filename)
                        if os.path.exists(thumb_path):
                            os.remove(thumb_path)
                            deleted_thumbs += 1
                            
                    except Exception as e:
                        errors.append(f"{video_path}: {str(e)}")
                
                # Delete analysis folders if requested
                if include_analysis:
                    analysis_base = os.path.join(storage_path, "_analysis")
                    if os.path.exists(analysis_base):
                        analysis_dirs = glob.glob(os.path.join(analysis_base, "analysis_*"))
                        for analysis_dir in analysis_dirs:
                            try:
                                # Check age filter for analysis folders
                                if cutoff_date:
                                    dir_name = os.path.basename(analysis_dir)
                                    match = re.search(r'analysis_(\d{8})', dir_name)
                                    if match:
                                        date_str = match.group(1)
                                        dir_date = datetime.strptime(date_str, "%Y%m%d")
                                        if dir_date >= cutoff_date:
                                            continue  # Skip newer analysis
                                
                                import shutil
                                shutil.rmtree(analysis_dir)
                                deleted_analysis += 1
                            except Exception as e:
                                errors.append(f"{analysis_dir}: {str(e)}")
                
                log_to_file(f"Deleted: {deleted_videos} videos, {deleted_thumbs} thumbs, {deleted_analysis} analysis folders. Errors: {len(errors)}")
                
            except Exception as e:
                log_to_file(f"Error in delete_all_recordings: {e}")
                _LOGGER.error(f"Error in delete_all_recordings: {e}")
                raise
            
            return {
                "deleted_videos": deleted_videos,
                "deleted_thumbnails": deleted_thumbs,
                "deleted_analysis": deleted_analysis,
                "errors": errors[:10]  # Limit error list
            }

        hass.services.async_register(DOMAIN, "delete_all_recordings", handle_delete_all_recordings)
        
        # 3. Register Motion Listeners (Auto-Record)
        
        # Helper to create proper closure
        def _create_motion_handler(cam_name, record_duration, snap_delay):
            async def _motion_changed(event):
                new_state = event.data.get("new_state")
                old_state = event.data.get("old_state")
                old_state_val = old_state.state if old_state else "None"
                new_state_val = new_state.state if new_state else "None"
                log_to_file(f"Motion state change: {event.data['entity_id']} [{old_state_val} -> {new_state_val}]")
                # Only trigger on actual off->on transition
                if new_state and new_state.state == "on" and old_state and old_state.state != "on":
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
                    
                    # Register listener and store unsubscribe callback for cleanup on reload
                    unsub = async_track_state_change_event(
                        hass, 
                        [motion_entity], 
                        _create_motion_handler(camera_target, record_duration, snap_delay)
                    )
                    entry.async_on_unload(unsub)
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
        
        # Run daily at same time - register with async_on_unload for cleanup on reload
        unsub_cleanup = async_track_time_interval(hass, run_cleanup, timedelta(hours=24))
        entry.async_on_unload(unsub_cleanup)

        # Auto Analysis Scheduler
        async def run_auto_analysis(now=None):
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

        async def _resolve_auto_device() -> str:
            if not analysis_auto_force_coral:
                return analysis_device
            devices = []
            if analysis_detector_url:
                devices = await _fetch_remote_devices(analysis_detector_url)
            if not devices:
                devices = await hass.async_add_executor_job(detect_available_devices)
            return "coral_usb" if "coral_usb" in devices else analysis_device

        def _person_entity_id(name: str) -> str:
            slug = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower())
            slug = re.sub(r"_+", "_", slug).strip("_")
            return f"binary_sensor.rtsp_recorder_person_{slug or 'unknown'}"

        def _set_person_entity(name: str, similarity: float | None, video_path: str | None, camera: str | None):
            if not person_entities_enabled:
                return
            entity_id = _person_entity_id(name)
            attrs = {
                "friendly_name": f"RTSP Person {name}",
                "person_name": name,
                "similarity": similarity,
                "camera": camera,
                "video_path": video_path,
                "last_seen": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            hass.states.async_set(entity_id, "on", attrs)
            timers = hass.data.setdefault(DOMAIN, {}).setdefault("person_entity_timers", {})
            if entity_id in timers:
                try:
                    timers[entity_id].cancel()
                except Exception:
                    pass
            timers[entity_id] = hass.loop.call_later(30, lambda: hass.states.async_set(entity_id, "off", attrs))

        def _extract_person_matches(result: dict) -> dict[str, dict[str, Any]]:
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

            # Fallback: support alternative layouts
            for face in (result.get("faces") or []):
                match = face.get("match") or {}
                name = match.get("name") or face.get("name") or face.get("person_name")
                similarity = match.get("similarity") if match else face.get("similarity")
                _add_match(name, similarity)

            return matches

        def _update_person_entities_from_result(result: dict) -> bool:
            if not person_entities_enabled:
                return False
            matches = _extract_person_matches(result)
            if not matches:
                return False
            for name, info in matches.items():
                _set_person_entity(name, info.get("similarity"), result.get("video_path"), None)
            return True

        def _update_person_entities_for_video(video_path: str | None):
            if not person_entities_enabled or not video_path:
                return
            try:
                result = _find_analysis_for_video(analysis_output_path, video_path)
                if result:
                    _update_person_entities_from_result(result)
            except Exception:
                pass

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
                vol.Optional("camera"): str,  # v1.0.6: Optional camera name for specific config
            }
        )
        @websocket_api.async_response
        async def ws_get_analysis_config(hass, connection, msg):
            """Return current analysis schedule configuration."""
            camera = msg.get("camera")
            
            # v1.0.6: Get camera-specific objects if camera is specified
            cam_objects = None
            if camera:
                safe_cam = camera.replace(" ", "_").replace("-", "_")
                cam_objects_key = f"analysis_objects_{safe_cam}"
                cam_objects = config_data.get(cam_objects_key, [])
            
            # v1.0.6: Build camera_objects map for all cameras
            camera_objects_map = {}
            for key, value in config_data.items():
                if key.startswith("analysis_objects_"):
                    cam_name = key.replace("analysis_objects_", "")
                    camera_objects_map[cam_name] = value
            
            result = {
                "analysis_enabled": analysis_enabled,
                "analysis_auto_enabled": analysis_auto_enabled,
                "analysis_auto_mode": analysis_auto_mode,
                "analysis_auto_time": analysis_auto_time,
                "analysis_auto_interval_hours": analysis_auto_interval_hours,
                "analysis_auto_since_days": analysis_auto_since_days,
                "analysis_auto_limit": analysis_auto_limit,
                "analysis_auto_skip_existing": analysis_auto_skip_existing,
                "analysis_auto_new": analysis_auto_new,
                "analysis_auto_force_coral": analysis_auto_force_coral,
                "person_entities_enabled": person_entities_enabled,
                "analysis_device": analysis_device,
                "analysis_objects": analysis_objects,
                "analysis_face_enabled": analysis_face_enabled,
                "analysis_face_confidence": analysis_face_confidence,
                "analysis_face_match_threshold": analysis_face_match_threshold,
                "analysis_face_store_embeddings": analysis_face_store_embeddings,
                "camera_objects": cam_objects,  # Specific camera objects (if requested)
                "camera_objects_map": camera_objects_map,  # All camera-specific settings
            }
            connection.send_result(msg["id"], result)

        websocket_api.async_register_command(hass, ws_get_analysis_config)

        # WebSocket API: People DB
        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/get_people",
            }
        )
        @websocket_api.async_response
        async def ws_get_people(hass, connection, msg):
            data = await _load_people_db(people_db_path)
            people_view = _public_people_view(data.get("people", []))
            log_to_file(f"WS get_people -> {people_view}")
            connection.send_result(msg["id"], {"people": people_view})

        websocket_api.async_register_command(hass, ws_get_people)

        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/add_person",
                vol.Required("name"): str,
            }
        )
        @websocket_api.async_response
        async def ws_add_person(hass, connection, msg):
            name = (msg.get("name") or "").strip()
            # MED-002 Fix: Validate name length and characters
            is_valid, error_msg = _validate_person_name(name)
            if not is_valid:
                connection.send_error(msg["id"], "invalid_name", error_msg)
                return
            data = await _load_people_db(people_db_path)
            person = {
                "id": uuid.uuid4().hex,
                "name": name,
                "created_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S"),
                "embeddings": [],
            }
            data.setdefault("people", []).append(person)
            await _save_people_db(people_db_path, data)
            connection.send_result(msg["id"], {"person": _public_people_view([person])[0]})

        websocket_api.async_register_command(hass, ws_add_person)

        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/rename_person",
                vol.Required("id"): vol.Any(str, int),
                vol.Required("name"): str,
            }
        )
        @websocket_api.async_response
        async def ws_rename_person(hass, connection, msg):
            person_id = str(msg.get("id"))
            name = (msg.get("name") or "").strip()
            # MED-002 Fix: Validate name length and characters
            is_valid, error_msg = _validate_person_name(name)
            if not is_valid:
                connection.send_error(msg["id"], "invalid_name", error_msg)
                return
            data = await _load_people_db(people_db_path)
            people = data.get("people", [])
            updated = None
            for p in people:
                if str(p.get("id")) == person_id:
                    p["name"] = name
                    updated = p
                    break
            if not updated:
                connection.send_error(msg["id"], "not_found", "Person nicht gefunden")
                return
            await _save_people_db(people_db_path, data)
            connection.send_result(msg["id"], {"person": _public_people_view([updated])[0]})

        websocket_api.async_register_command(hass, ws_rename_person)

        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/delete_person",
                vol.Required("id"): vol.Any(str, int),
                vol.Optional("name"): str,
                vol.Optional("created_utc"): str,
            }
        )
        @websocket_api.async_response
        async def ws_delete_person(hass, connection, msg):
            log_to_file(f"WS delete_person payload: {msg}")
            person_id = str(msg.get("id"))
            name = (msg.get("name") or "").strip()
            created_utc = (msg.get("created_utc") or "").strip()
            data = await _load_people_db(people_db_path)
            people = data.get("people", [])
            new_people = [p for p in people if str(p.get("id")) != person_id]
            if len(new_people) == len(people):
                # Fallback: accept numeric index from UI
                if person_id.isdigit():
                    idx = int(person_id)
                    if 0 <= idx < len(people):
                        new_people = [p for i, p in enumerate(people) if i != idx]
                    else:
                        new_people = people
                else:
                    new_people = people

            if len(new_people) == len(people) and (name or created_utc):
                def _match(p: dict[str, Any]) -> bool:
                    if created_utc and p.get("created_utc") == created_utc:
                        return True
                    if name and p.get("name") == name:
                        return True
                    return False
                new_people = [p for p in people if not _match(p)]

            if len(new_people) == len(people):
                connection.send_error(msg["id"], "not_found", "Person nicht gefunden")
                return
            data["people"] = new_people
            await _save_people_db(people_db_path, data)
            connection.send_result(msg["id"], {"deleted": True})

        websocket_api.async_register_command(hass, ws_delete_person)

        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/add_person_embedding",
                vol.Required("person_id"): vol.Any(str, int),
                vol.Required("embedding"): list,
                vol.Optional("name"): str,
                vol.Optional("created_utc"): str,
                vol.Optional("thumb"): str,
                vol.Optional("source", default="manual"): str,
            }
        )
        @websocket_api.async_response
        async def ws_add_person_embedding(hass, connection, msg):
            log_to_file(f"INIT: add_person_embedding called with person_id={msg.get('person_id')}, embedding_len={len(msg.get('embedding') or [])}")
            try:
                person_id = str(msg.get("person_id"))
                name = (msg.get("name") or "").strip()
                created_utc = (msg.get("created_utc") or "").strip()
                thumb = msg.get("thumb")
                embedding = msg.get("embedding") or []
                try:
                    embedding = [float(v) for v in embedding]
                except Exception:
                    connection.send_error(msg["id"], "invalid_embedding", "Embedding ungueltig")
                    return
                embedding = _normalize_embedding_simple(embedding)
                if not embedding:
                    connection.send_error(msg["id"], "invalid_embedding", "Embedding ungueltig")
                    return
                data = await _load_people_db(people_db_path)
                people = data.get("people", [])
                updated = None
                def _append_embedding(p: dict[str, Any]) -> None:
                    entry = {"vector": embedding, "source": msg.get("source")}
                    if thumb:
                        entry["thumb"] = thumb
                    entry["created_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
                    p.setdefault("embeddings", []).append(entry)

                for p in people:
                    if str(p.get("id")) == person_id:
                        _append_embedding(p)
                        _update_person_centroid(p)  # Update centroid after adding embedding
                        updated = p
                        break
                if not updated and (name or created_utc):
                    for p in people:
                        if created_utc and p.get("created_utc") == created_utc:
                            _append_embedding(p)
                            _update_person_centroid(p)  # Update centroid after adding embedding
                            updated = p
                            break
                        if name and p.get("name") == name:
                            _append_embedding(p)
                            _update_person_centroid(p)  # Update centroid after adding embedding
                            updated = p
                            break
                if not updated:
                    connection.send_error(msg["id"], "not_found", "Person nicht gefunden")
                    return
                await _save_people_db(people_db_path, data)
                
                # Send success response immediately (don't wait for re-matching)
                connection.send_result(msg["id"], {"person": _public_people_view([updated])[0]})
                
                # Re-match all faces in background (fire-and-forget)
                async def _background_rematch():
                    try:
                        updated_analyses = await _update_all_face_matches(
                            analysis_output_path, 
                            data.get("people", []), 
                            analysis_face_match_threshold
                        )
                        log_to_file(f"INIT: Re-matched faces in {updated_analyses} analysis files after training")
                    except Exception as e:
                        log_to_file(f"INIT: Background re-match error: {e}")
                
                hass.async_create_task(_background_rematch())
                
            except Exception as exc:
                log_to_file(f"INIT: add_person_embedding ERROR: {type(exc).__name__}: {exc}")
                connection.send_error(msg["id"], "error", f"{type(exc).__name__}: {exc}")

        websocket_api.async_register_command(hass, ws_add_person_embedding)

        # WebSocket API: Add negative sample (mark face as "NOT this person")
        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/add_negative_sample",
                vol.Required("person_id"): str,
                vol.Required("embedding"): list,
                vol.Optional("thumb"): str,
                vol.Optional("source"): str,
            }
        )
        @websocket_api.async_response
        async def ws_add_negative_sample(hass, connection, msg):
            """Add a negative sample to a person (mark as 'NOT this person')."""
            log_to_file(f"INIT: add_negative_sample called for person_id={msg.get('person_id')}")
            try:
                person_id = str(msg.get("person_id"))
                embedding = msg.get("embedding") or []
                thumb = msg.get("thumb")
                source = msg.get("source", "manual")
                
                try:
                    embedding = [float(v) for v in embedding]
                except Exception:
                    connection.send_error(msg["id"], "invalid_embedding", "Embedding ungueltig")
                    return
                
                embedding = _normalize_embedding_simple(embedding)
                if not embedding:
                    connection.send_error(msg["id"], "invalid_embedding", "Embedding ungueltig")
                    return
                
                data = await _load_people_db(people_db_path)
                people = data.get("people", [])
                updated = None
                
                for p in people:
                    if str(p.get("id")) == person_id:
                        entry = {
                            "vector": embedding,
                            "source": source,
                            "created_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
                        }
                        if thumb:
                            entry["thumb"] = thumb
                        p.setdefault("negative_embeddings", []).append(entry)
                        updated = p
                        break
                
                if not updated:
                    connection.send_error(msg["id"], "not_found", "Person nicht gefunden")
                    return
                
                await _save_people_db(people_db_path, data)
                
                neg_count = len(updated.get("negative_embeddings", []))
                log_to_file(f"INIT: Added negative sample to {updated.get('name')} (total: {neg_count})")
                
                connection.send_result(msg["id"], {
                    "success": True,
                    "person_id": person_id,
                    "negative_count": neg_count
                })
                
            except Exception as exc:
                log_to_file(f"INIT: add_negative_sample ERROR: {type(exc).__name__}: {exc}")
                connection.send_error(msg["id"], "error", f"{type(exc).__name__}: {exc}")

        websocket_api.async_register_command(hass, ws_add_negative_sample)

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
                vol.Optional("analysis_auto_new"): bool,
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
                    "analysis_auto_new",
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

        # v1.0.6: WebSocket API: Set Camera-Specific Objects
        @websocket_api.websocket_command(
            {
                vol.Required("type"): "rtsp_recorder/set_camera_objects",
                vol.Required("camera"): str,
                vol.Required("objects"): list,
            }
        )
        @websocket_api.async_response
        async def ws_set_camera_objects(hass, connection, msg):
            """Set camera-specific analysis objects."""
            try:
                camera = msg["camera"]
                objects = msg["objects"]
                
                # Create safe key
                safe_cam = camera.replace(" ", "_").replace("-", "_")
                cam_objects_key = f"analysis_objects_{safe_cam}"
                
                # Update config
                new_data = dict(entry.data)
                new_options = dict(entry.options) if entry.options else {}
                
                if objects:  # Non-empty list = use specific objects
                    new_data[cam_objects_key] = objects
                    new_options[cam_objects_key] = objects
                else:  # Empty list = use global objects
                    new_data.pop(cam_objects_key, None)
                    new_options.pop(cam_objects_key, None)
                
                hass.config_entries.async_update_entry(entry, data=new_data, options=new_options)
                
                log_to_file(f"Set camera objects for {camera}: {objects}")
                
                connection.send_result(msg["id"], {
                    "success": True,
                    "camera": camera,
                    "objects": objects,
                    "message": f"Objects for {camera} updated"
                })
            except Exception as e:
                log_to_file(f"Set camera objects error: {e}")
                connection.send_result(msg["id"], {
                    "success": False,
                    "message": str(e)
                })

        websocket_api.async_register_command(hass, ws_set_camera_objects)

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
