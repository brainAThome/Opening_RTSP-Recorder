import asyncio
import logging
import os

_LOGGER = logging.getLogger(__name__)

def log_to_file(msg):
    """Fallback logging to file."""
    try:
        with open("/config/rtsp_debug.log", "a") as f:
            f.write(f"RECORDER: {msg}\n")
    except Exception:
        pass

async def _monitor_recording(process, tmp_path, final_path):
    """Wait for process to finish, then rename file."""
    try:
        await process.wait()
        log_to_file(f"FFmpeg finished with code {process.returncode}")
        
        # Check if file exists and has size > 0
        if os.path.exists(tmp_path):
            size = os.path.getsize(tmp_path)
            log_to_file(f"Temp file size: {size} bytes")
            
            if size > 0:
                try:
                    os.rename(tmp_path, final_path)
                    log_to_file(f"Renamed {tmp_path} -> {final_path} (Success)")
                except Exception as e:
                    log_to_file(f"RENAME ERROR: {e}")
            else:
                 log_to_file(f"Temp file empty, deleting.")
                 os.remove(tmp_path)
        else:
            log_to_file(f"WARNING: Tmp file missing: {tmp_path}")

    except Exception as e:
        log_to_file(f"MONITOR ERROR: {e}")

async def async_record_stream(hass, rtsp_url, duration, output_path):
    """Record an RTSP stream using FFmpeg."""
    
    # Use .tmp extension while recording
    tmp_path = output_path + ".tmp"
    
    command = [
        "ffmpeg",
        "-y",
        "-t", str(duration),
        "-i", rtsp_url,
        "-c", "copy",
        "-f", "mp4",  # EXPLICITLY set format since ext is .tmp
        tmp_path
    ]
    
    log_to_file(f"START RECORD: {rtsp_url} -> {tmp_path}")
    
    # Ensure directory exists
    folder = os.path.dirname(output_path)
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    
    # Create background task to handle the rename when finished
    hass.async_create_task(_monitor_recording(process, tmp_path, output_path))
    
    return process

async def async_take_snapshot(hass, rtsp_url, output_path, delay=0):
    """Take a snapshot using FFmpeg after an optional delay."""
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
