"""Helper utilities for RTSP Recorder Integration.

This module contains utility functions used across the integration:
- Logging
- System stats
- Path validation
- Input validation
- Time parsing
- Video file listing
- Inference stats tracking
"""
import asyncio
import logging
import os
import time as _time
from collections import deque as _deque
import threading as _threading
from typing import Any

from .const import (
    IS_LINUX,
    MAX_PERSON_NAME_LENGTH,
    VALID_NAME_PATTERN,
    MAX_CONCURRENT_ANALYSES,
)

_LOGGER = logging.getLogger(__name__)


# ===== Rate Limiting (MED-004 Fix) =====
_analysis_semaphore: asyncio.Semaphore | None = None


def _get_analysis_semaphore() -> asyncio.Semaphore:
    """Get or create the analysis semaphore."""
    global _analysis_semaphore
    if _analysis_semaphore is None:
        _analysis_semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANALYSES)
    return _analysis_semaphore


# ===== Inference Stats Tracker =====
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
    
    def get_stats(self) -> dict[str, Any]:
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


# Global singleton
_inference_stats = InferenceStatsTracker()


def get_inference_stats() -> InferenceStatsTracker:
    """Get the global inference stats tracker instance."""
    return _inference_stats


# ===== System Stats =====
def _get_system_stats_sync() -> dict[str, Any]:
    """Read system stats (Linux: /proc, other platforms: defaults)."""
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
        _time.sleep(0.1)  # Safe: runs in executor thread, not event loop
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


def get_system_stats() -> dict[str, Any]:
    """Get system stats (wrapper for sync contexts)."""
    return _get_system_stats_sync()


# ===== Logging =====
def log_to_file(msg: str) -> None:
    """Log message to both standard logger and fallback debug file.
    
    This dual logging approach ensures messages are captured by Home
    Assistant's debug logging system while also maintaining a persistent
    file log for troubleshooting deployment issues.
    """
    # Write to standard logger for "Enable Debug Logging" support
    _LOGGER.debug(msg)
    
    # Keep file logging for fallback
    try:
        def _write_log():
            with open("/config/rtsp_debug.log", "a") as f:
                f.write(f"RTSP: {msg}\n")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(_write_log))
        except RuntimeError:
            _write_log()
    except Exception:
        pass


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


# ===== Input Validation (MED-002 Fix) =====
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


# ===== Time Parsing =====
def _parse_hhmm(value: str) -> tuple[int, int] | None:
    """Parse HH:MM time string to (hour, minute) tuple."""
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


# ===== File Listing =====
def _list_video_files(storage_path: str, camera: str | None = None) -> list[str]:
    """List all MP4 video files in storage path, optionally filtered by camera."""
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
