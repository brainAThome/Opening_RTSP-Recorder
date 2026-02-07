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
_analysis_semaphore_limit: int | None = None


def _get_analysis_semaphore() -> asyncio.Semaphore:
    """Get or create the analysis semaphore.
    
    Returns:
        asyncio.Semaphore: The analysis semaphore instance
    """
    global _analysis_semaphore
    limit = _analysis_semaphore_limit or MAX_CONCURRENT_ANALYSES
    if _analysis_semaphore is None:
        _analysis_semaphore = asyncio.Semaphore(limit)
    return _analysis_semaphore


def _set_analysis_semaphore_limit(limit: int) -> None:
    """Set the max concurrent analyses limit and reset semaphore if needed.
    
    Args:
        limit: Maximum number of concurrent analyses
    """
    global _analysis_semaphore, _analysis_semaphore_limit
    try:
        new_limit = max(1, int(limit))
    except Exception:
        new_limit = MAX_CONCURRENT_ANALYSES

    if _analysis_semaphore_limit != new_limit:
        _analysis_semaphore_limit = new_limit
        _analysis_semaphore = asyncio.Semaphore(new_limit)


# ===== Inference Stats Tracker =====
class InferenceStatsTracker:
    """Track inference statistics for performance monitoring."""
    
    # v1.1.0: Erhöht von 100 auf 1000, damit bei intensiver Analyse
    # alle Inferenzen der letzten 60s erfasst werden können.
    # Bei 60fps Analyse = 60 Frames pro Video, 10 Videos = 600 Einträge
    def __init__(self, max_history: int = 1000) -> None:
        self._lock = _threading.Lock()
        self._history = _deque(maxlen=max_history)
        self._total_inferences = 0
        self._coral_inferences = 0
        self._cpu_inferences = 0
        self._last_device = "none"
        self._start_time = _time.time()
    
    def record(self, device: str, duration_ms: float, frame_count: int = 1) -> None:
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
            
            # v1.1.0m: TPU Load calculation (actual chip busy time)
            # 
            # Berechnung: (Summe Coral-Inferenz-Zeit) / (Zeitfenster) × 100
            #
            # Beispiel: Bei 95ms Inferenz alle 2s = 95/2000 = 4.75% Last
            # Bei kontinuierlicher Analyse: ~50-100ms pro Batch, alle 1-2s
            #
            # Nur Coral-Inferenzen zählen, nicht CPU-Inferenzen!
            # v1.1.0m: 5s Fenster für reaktive Anzeige (schnelles Abklingen wenn Analyse stoppt)
            TPU_WINDOW_SECONDS = 5
            recent_coral_window = [h for h in self._history if now - h["timestamp"] < TPU_WINDOW_SECONDS and h["device"] == "coral_usb"]
            # WICHTIG: duration_ms ist BEREITS die Gesamtzeit für den Batch, NICHT pro Frame!
            coral_busy_ms = sum(h["duration_ms"] for h in recent_coral_window)
            
            # Zeitfenster = 5 Sekunden = 5000 ms (reaktive Anzeige)
            # Aber wenn uptime < 5s, dann nur uptime verwenden
            time_window_ms = min(float(TPU_WINDOW_SECONDS), uptime) * 1000.0
            
            tpu_load_pct = 0.0
            if time_window_ms > 0 and coral_busy_ms > 0:
                tpu_load_pct = round(100.0 * coral_busy_ms / time_window_ms, 2)
                # Cap at 100% (theoretisch nicht möglich, aber sicherheitshalber)
                tpu_load_pct = min(tpu_load_pct, 100.0)
            
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
                "tpu_load_pct": tpu_load_pct,  # NEU: Echte TPU-Chip-Auslastung
            }


# Global singleton
_inference_stats = InferenceStatsTracker()


def get_inference_stats() -> InferenceStatsTracker:
    """Get the global inference stats tracker instance."""
    return _inference_stats


# ===== System Stats =====
# v1.1.0m: Rolling average for smoother CPU readings
# Mit 2s Polling: 10 Samples = 20 Sekunden Mittelung → glatte Anzeige ohne Spitzen
_cpu_history: list[float] = []
_ram_history: list[float] = []
_CPU_HISTORY_SIZE = 10  # Average over last 10 readings (20s at 2s polling)


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
        _time.sleep(0.3)  # v1.1.0: Increased from 0.1s to 0.3s for better accuracy
        idle2, total2 = read_cpu()
        
        idle_delta = idle2 - idle1
        total_delta = total2 - total1
        if total_delta > 0:
            current_cpu = 100.0 * (1.0 - idle_delta / total_delta)
            
            # v1.1.0m: Rolling average for smoother, more accurate readings
            _cpu_history.append(current_cpu)
            if len(_cpu_history) > _CPU_HISTORY_SIZE:
                _cpu_history.pop(0)
            
            stats["cpu_percent"] = round(sum(_cpu_history) / len(_cpu_history), 1)
        
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
            current_ram = 100.0 * used_kb / total_kb
            # v1.1.0m: Rolling average for RAM too
            _ram_history.append(current_ram)
            if len(_ram_history) > _CPU_HISTORY_SIZE:
                _ram_history.pop(0)
            stats["memory_percent"] = round(sum(_ram_history) / len(_ram_history), 1)
            
    except Exception:
        pass  # Return default stats on error
    
    return stats

def get_system_stats() -> dict[str, Any]:
    """Get system stats (wrapper for sync contexts)."""
    return _get_system_stats_sync()


# ===== Logging =====
# LOW-001 Fix: Log rotation constants
_LOG_FILE_PATH = "/config/rtsp_debug.log"
_LOG_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB max log file size
_LOG_BACKUP_PATH = "/config/rtsp_debug.log.old"


def _rotate_log_if_needed() -> None:
    """Rotate log file if it exceeds max size (LOW-001 Fix)."""
    try:
        if os.path.exists(_LOG_FILE_PATH):
            size = os.path.getsize(_LOG_FILE_PATH)
            if size > _LOG_MAX_SIZE_BYTES:
                # Rename current log to .old (overwriting previous .old)
                if os.path.exists(_LOG_BACKUP_PATH):
                    os.remove(_LOG_BACKUP_PATH)
                os.rename(_LOG_FILE_PATH, _LOG_BACKUP_PATH)
    except OSError:
        pass  # Rotation failure should not break logging


def log_to_file(msg: str) -> None:
    """Log message to both standard logger and fallback debug file.
    
    This dual logging approach ensures messages are captured by Home
    Assistant's debug logging system while also maintaining a persistent
    file log for troubleshooting deployment issues.
    
    LOW-001 Fix: Implements log rotation at 10MB to prevent unbounded growth.
    """
    # Write to standard logger for "Enable Debug Logging" support
    _LOGGER.debug(msg)
    
    # Keep file logging for fallback with rotation check
    try:
        def _write_log():
            _rotate_log_if_needed()
            with open(_LOG_FILE_PATH, "a") as f:
                f.write(f"RTSP: {msg}\n")

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(_write_log))
        except RuntimeError:
            _write_log()
    except Exception as e:
        # Log write failed - cannot log this recursively, print to stderr
        import sys
        print(f"RTSP Recorder log_to_file failed: {e}", file=sys.stderr)


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
    except (ValueError, TypeError):
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


# ===== Database Backup (SEC-005 Fix) =====
import shutil
from datetime import datetime

_BACKUP_DIR = "/config/rtsp_recorder/backups"
_MAX_BACKUPS = 7  # Keep last 7 backups


def backup_database(db_path: str = "/config/rtsp_recorder/rtsp_recorder.db") -> bool:
    """Create a backup of the SQLite database.

    Implements SEC-005: Automatic database backups to prevent data loss.
    Keeps the last 7 backups and rotates older ones.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        True if backup was successful, False otherwise
    """
    try:
        if not os.path.exists(db_path):
            log_to_file(f"Backup skipped: DB not found at {db_path}")
            return False

        # Create backup directory if needed
        if not os.path.exists(_BACKUP_DIR):
            os.makedirs(_BACKUP_DIR)

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"rtsp_recorder_{timestamp}.db"
        backup_path = os.path.join(_BACKUP_DIR, backup_name)

        # Copy database file
        shutil.copy2(db_path, backup_path)

        # Also copy WAL file if it exists
        wal_path = db_path + "-wal"
        if os.path.exists(wal_path):
            shutil.copy2(wal_path, backup_path + "-wal")

        log_to_file(f"Database backup created: {backup_name}")

        # Rotate old backups (keep only MAX_BACKUPS)
        _rotate_backups()

        return True

    except Exception as e:
        log_to_file(f"Database backup failed: {e}")
        return False


def _rotate_backups() -> None:
    """Remove old backups, keeping only the most recent ones."""
    try:
        if not os.path.exists(_BACKUP_DIR):
            return

        # Get all backup files sorted by modification time
        backups = []
        for f in os.listdir(_BACKUP_DIR):
            if f.startswith("rtsp_recorder_") and f.endswith(".db"):
                path = os.path.join(_BACKUP_DIR, f)
                backups.append((os.path.getmtime(path), path))

        # Sort by time (newest first)
        backups.sort(reverse=True)

        # Remove backups beyond MAX_BACKUPS
        for _, path in backups[_MAX_BACKUPS:]:
            try:
                os.remove(path)
                # Also remove WAL if exists
                wal = path + "-wal"
                if os.path.exists(wal):
                    os.remove(wal)
                log_to_file(f"Removed old backup: {os.path.basename(path)}")
            except OSError:
                pass

    except Exception as e:
        log_to_file(f"Backup rotation failed: {e}")
