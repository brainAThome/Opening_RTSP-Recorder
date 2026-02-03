"""RTSP stream recording module for RTSP Recorder Integration.

This module provides async functions for recording RTSP streams and
taking snapshots using FFmpeg. Recordings use a temporary file strategy
to prevent incomplete files from appearing in the media library.
"""
import asyncio
import logging
import os
import shutil
from typing import Callable, Optional, Any

_LOGGER = logging.getLogger(__name__)

# Type alias for recording completion callback
# Signature: (output_path: str, success: bool, error_msg: Optional[str]) -> None
RecordingCallback = Callable[[str, bool, Optional[str]], None]

# LOW-002 Fix: Cache FFmpeg availability
_ffmpeg_available: bool | None = None


async def check_ffmpeg_available() -> bool:
    """Check if FFmpeg is available on the system (LOW-002 Fix).
    
    Returns:
        True if FFmpeg is available and working, False otherwise.
    
    Note:
        Result is cached after first check for performance.
    """
    global _ffmpeg_available
    
    if _ffmpeg_available is not None:
        return _ffmpeg_available
    
    # First check: shutil.which (fast)
    if not shutil.which("ffmpeg"):
        _LOGGER.warning("FFmpeg not found in PATH")
        _ffmpeg_available = False
        return False
    
    # Second check: actually run ffmpeg -version
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(process.wait(), timeout=5.0)
        _ffmpeg_available = (process.returncode == 0)
        if not _ffmpeg_available:
            _LOGGER.warning("FFmpeg returned non-zero exit code")
    except asyncio.TimeoutError:
        _LOGGER.warning("FFmpeg check timed out")
        _ffmpeg_available = False
    except Exception as e:
        _LOGGER.warning("FFmpeg check failed: %s", e)
        _ffmpeg_available = False
    
    if _ffmpeg_available:
        _LOGGER.debug("FFmpeg is available")
    
    return _ffmpeg_available


def log_to_file(msg: str) -> None:
    """Write debug message to fallback log file.
    
    Args:
        msg: Message to log
    
    Note:
        This is a fallback for debugging when standard logging
        is not available or for persistent debug logs.
    """
    try:
        with open("/config/rtsp_debug.log", "a") as f:
            f.write(f"RECORDER: {msg}\n")
    except OSError:
        pass

async def _monitor_recording(
    process: asyncio.subprocess.Process,
    tmp_path: str,
    final_path: str,
    on_complete: Optional[RecordingCallback] = None
) -> None:
    """Monitor FFmpeg process and finalize recording on completion.
    
    Waits for the FFmpeg process to finish, validates the output file,
    and renames it from temporary to final path. Handles errors gracefully
    and notifies caller via optional callback.
    
    Args:
        process: The running FFmpeg subprocess
        tmp_path: Path to temporary recording file (.tmp extension)
        final_path: Final destination path for the recording
        on_complete: Optional callback invoked when recording finishes.
                    Called with (output_path, success, error_msg).
    
    Note:
        Empty or failed recordings are automatically cleaned up.
        The callback is always invoked if provided, even on failure.
    """
    error_msg = None
    success = False
    
    try:
        # Wait for process and capture stderr for debugging
        stdout, stderr = await process.communicate()
        log_to_file(f"FFmpeg finished with code {process.returncode}")
        
        if process.returncode != 0:
            error_msg = f"FFmpeg exited with code {process.returncode}"
            # Log last 500 chars of stderr for debugging
            if stderr:
                stderr_text = stderr.decode('utf-8', errors='replace')[-500:]
                log_to_file(f"FFmpeg STDERR: {stderr_text}")
            log_to_file(f"FFmpeg ERROR: {error_msg}")
        
        # Check if file exists and has size > 0
        if os.path.exists(tmp_path):
            size = os.path.getsize(tmp_path)
            log_to_file(f"Temp file size: {size} bytes")
            
            if size > 0:
                try:
                    os.rename(tmp_path, final_path)
                    log_to_file(f"Renamed {tmp_path} -> {final_path} (Success)")
                    success = True
                except OSError as e:
                    error_msg = f"Rename failed: {e}"
                    log_to_file(f"RENAME ERROR: {e}")
            else:
                error_msg = "Recording file is empty"
                log_to_file(f"Temp file empty, deleting.")
                os.remove(tmp_path)
        else:
            error_msg = f"Temp file missing: {tmp_path}"
            log_to_file(f"WARNING: {error_msg}")

    except Exception as e:
        error_msg = f"Monitor error: {e}"
        log_to_file(f"MONITOR ERROR: {e}")
    
    # Notify caller of result (HIGH-003 Fix)
    if on_complete:
        try:
            on_complete(final_path, success, error_msg)
        except Exception as cb_err:
            log_to_file(f"Callback error: {cb_err}")


async def async_record_stream(
    hass: Any,
    rtsp_url: str,
    duration: int,
    output_path: str,
    on_complete: Optional[RecordingCallback] = None
) -> asyncio.subprocess.Process:
    """Record an RTSP stream using FFmpeg.
    
    Starts an FFmpeg process to record the specified RTSP stream.
    Uses a temporary file during recording to prevent incomplete
    files from appearing in the media library.
    
    Args:
        hass: Home Assistant instance (used for task creation)
        rtsp_url: Full RTSP stream URL to record
        duration: Recording duration in seconds
        output_path: Final destination path for the recording (.mp4)
        on_complete: Optional callback invoked when recording finishes.
                    Signature: (path, success, error_msg) -> None
    
    Returns:
        The FFmpeg subprocess object (recording continues in background)
    
    Example:
        >>> process = await async_record_stream(
        ...     hass, "rtsp://camera/stream", 60, "/media/recording.mp4"
        ... )
    """
    
    # Use .tmp extension while recording
    tmp_path = output_path + ".tmp"
    
    # FIX: Improved FFmpeg command with proper RTSP options
    # -rtsp_transport tcp: Use TCP for more reliable streaming
    # -timeout: Connection timeout in microseconds (5 seconds)
    # -t after -i: Duration as output option for more reliable recording
    command = [
        "ffmpeg",
        "-y",                           # Overwrite output
        "-rtsp_transport", "tcp",       # Use TCP for RTSP (more reliable)
        "-timeout", "5000000",          # 5 second connection timeout
        "-i", rtsp_url,                 # Input RTSP stream
        "-t", str(duration),            # Recording duration (as output option)
        "-c", "copy",                   # Copy codec (no re-encoding)
        "-f", "mp4",                    # Output format (important for .tmp extension)
        "-movflags", "+faststart",      # Enable fast start for web playback
        tmp_path
    ]
    
    log_to_file(f"START RECORD: duration={duration}s, url={rtsp_url[:50]}..., output={tmp_path}")
    
    # Ensure directory exists
    folder = os.path.dirname(output_path)
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        log_to_file(f"FFmpeg process started with PID: {process.pid}")
    except Exception as e:
        log_to_file(f"CRITICAL: Failed to start FFmpeg: {e}")
        raise
    
    # Create background task to handle the rename when finished
    hass.async_create_task(_monitor_recording(process, tmp_path, output_path, on_complete))
    
    return process

async def async_take_snapshot(
    hass: Any,
    rtsp_url: str,
    output_path: str,
    delay: float = 0
) -> None:
    """Capture a single frame snapshot from an RTSP stream.
    
    Uses FFmpeg to capture one frame from the stream and save it
    as an image file. Supports an optional delay before capture.
    
    Args:
        hass: Home Assistant instance (reserved for future use)
        rtsp_url: Full RTSP stream URL
        output_path: Destination path for the snapshot image
        delay: Seconds to wait before capturing (default 0)
    
    Note:
        The delay is useful when you want to capture a frame
        a few seconds into a recording or event.
    """
    if delay > 0:
        await asyncio.sleep(delay)

    command = [
        "ffmpeg",
        "-y",
        "-i", rtsp_url,
        "-vframes", "1",
        output_path
    ]
    
    log_to_file(f"SNAPSHOT: {output_path}")

    folder = os.path.dirname(output_path)
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await process.wait()


# ===== Cleanup Functions (MED-007 Fix) =====
def cleanup_orphaned_tmp_files(recordings_path: str, max_age_hours: int = 24) -> int:
    """Clean up orphaned temporary files from interrupted recordings.
    
    Walks the recordings directory and removes .tmp files that are
    older than the specified age. These files are typically left over
    from recordings that were interrupted or failed.
    
    Args:
        recordings_path: Base directory containing recordings
        max_age_hours: Minimum age in hours before a .tmp file is deleted.
                      Default 24 hours to avoid deleting active recordings.
    
    Returns:
        Number of files successfully deleted
    
    Note:
        This function logs each deleted file for debugging purposes.
        Files that cannot be deleted (e.g., permissions) are logged but
        do not prevent cleanup of other files.
    """
    import time
    deleted: int = 0
    now = time.time()
    max_age_seconds = max_age_hours * 3600
    
    try:
        for root, dirs, files in os.walk(recordings_path):
            for filename in files:
                if filename.endswith('.tmp'):
                    filepath = os.path.join(root, filename)
                    try:
                        file_age = now - os.path.getmtime(filepath)
                        if file_age > max_age_seconds:
                            os.remove(filepath)
                            log_to_file(f"Cleaned up orphaned tmp file: {filepath}")
                            deleted += 1
                    except OSError as e:
                        log_to_file(f"Error cleaning tmp file {filepath}: {e}")
    except Exception as e:
        log_to_file(f"Error during tmp cleanup: {e}")
    
    return deleted
# ===== End Cleanup Functions =====
