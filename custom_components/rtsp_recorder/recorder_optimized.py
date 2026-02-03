"""Optimized RTSP stream recording module with event-driven architecture.

KEY IMPROVEMENTS:
1. Early Thumbnail: Generate preview within 2s of recording start
2. Callback-based: No more polling/sleep - FFmpeg completion triggers next step
3. Parallel Operations: Snapshot + Analysis can run concurrently
4. Watchdog: Auto-cleanup of stale recordings
5. Robust Error Handling: Retry mechanisms for transient failures
"""
import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Any, Dict
from enum import Enum

_LOGGER = logging.getLogger(__name__)


class RecordingState(Enum):
    """Recording lifecycle states."""
    STARTING = "starting"
    RECORDING = "recording"
    FINALIZING = "finalizing"
    THUMBNAIL_PENDING = "thumbnail_pending"
    ANALYZING = "analyzing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class RecordingJob:
    """Represents an active recording with all metadata."""
    camera_name: str
    output_path: str
    duration: int
    rtsp_url: str
    started_at: datetime = field(default_factory=datetime.now)
    state: RecordingState = RecordingState.STARTING
    process: Optional[asyncio.subprocess.Process] = None
    early_thumbnail_path: Optional[str] = None
    final_thumbnail_path: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def tmp_path(self) -> str:
        return self.output_path + ".tmp"
    
    @property
    def elapsed_seconds(self) -> float:
        return (datetime.now() - self.started_at).total_seconds()
    
    @property
    def expected_end(self) -> datetime:
        from datetime import timedelta
        return self.started_at + timedelta(seconds=self.duration)
    
    @property
    def is_overdue(self) -> bool:
        """Check if recording should have finished but hasn't."""
        return self.elapsed_seconds > (self.duration + 30)  # 30s grace period


# Global registry of active recordings
_active_jobs: Dict[str, RecordingJob] = {}

# Callbacks for external notification
RecordingStartCallback = Callable[[RecordingJob], None]
RecordingCompleteCallback = Callable[[RecordingJob, bool], None]
ThumbnailReadyCallback = Callable[[RecordingJob, str], None]


class OptimizedRecorder:
    """Event-driven recorder with parallel processing capabilities."""
    
    def __init__(
        self,
        hass: Any,
        on_recording_start: Optional[RecordingStartCallback] = None,
        on_early_thumbnail: Optional[ThumbnailReadyCallback] = None,
        on_recording_complete: Optional[RecordingCompleteCallback] = None,
        on_final_thumbnail: Optional[ThumbnailReadyCallback] = None,
    ):
        self.hass = hass
        self.on_recording_start = on_recording_start
        self.on_early_thumbnail = on_early_thumbnail
        self.on_recording_complete = on_recording_complete
        self.on_final_thumbnail = on_final_thumbnail
        self._watchdog_task: Optional[asyncio.Task] = None
        
    async def start(self) -> None:
        """Start the recorder (including watchdog)."""
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        _LOGGER.info("OptimizedRecorder started with watchdog")
        
    async def stop(self) -> None:
        """Stop the recorder and cleanup."""
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        _LOGGER.info("OptimizedRecorder stopped")
    
    async def record(
        self,
        camera_name: str,
        rtsp_url: str,
        duration: int,
        output_path: str,
        thumbnail_path: str,
    ) -> RecordingJob:
        """Start a new recording with early thumbnail generation.
        
        This method returns IMMEDIATELY after starting the recording.
        Completion is signaled via callbacks.
        
        Flow:
        1. Start FFmpeg recording → Return immediately
        2. After 2s: Generate early thumbnail → Callback
        3. After duration+buffer: Finalize recording → Callback
        4. Generate final thumbnail from video → Callback
        """
        job = RecordingJob(
            camera_name=camera_name,
            output_path=output_path,
            duration=duration,
            rtsp_url=rtsp_url,
            final_thumbnail_path=thumbnail_path,
        )
        
        _active_jobs[output_path] = job
        
        # Start recording in background (non-blocking)
        asyncio.create_task(self._execute_recording(job))
        
        # Notify: Recording started
        if self.on_recording_start:
            self.on_recording_start(job)
        
        return job
    
    async def _execute_recording(self, job: RecordingJob):
        """Execute the full recording pipeline."""
        try:
            # PHASE 1: Start FFmpeg
            job.state = RecordingState.RECORDING
            job.process = await self._start_ffmpeg(job)
            
            if not job.process:
                job.state = RecordingState.FAILED
                job.error = "Failed to start FFmpeg"
                return
            
            # PHASE 2: Early thumbnail (after 2 seconds) - PARALLEL
            asyncio.create_task(self._generate_early_thumbnail(job))
            
            # PHASE 3: Wait for FFmpeg to complete (callback-based)
            await self._monitor_ffmpeg(job)
            
            # PHASE 4: Finalize recording (rename .tmp to .mp4)
            job.state = RecordingState.FINALIZING
            success = await self._finalize_recording(job)
            
            if success:
                # PHASE 5: Generate final thumbnail from video
                job.state = RecordingState.THUMBNAIL_PENDING
                await self._generate_final_thumbnail(job)
                
                job.state = RecordingState.COMPLETE
            else:
                job.state = RecordingState.FAILED
            
            # Notify: Recording complete
            if self.on_recording_complete:
                self.on_recording_complete(job, success)
                
        except Exception as e:
            _LOGGER.exception("Recording pipeline failed: %s", e)
            job.state = RecordingState.FAILED
            job.error = str(e)
            if self.on_recording_complete:
                self.on_recording_complete(job, False)
        finally:
            # Cleanup from registry
            _active_jobs.pop(job.output_path, None)
    
    async def _start_ffmpeg(self, job: RecordingJob) -> Optional[asyncio.subprocess.Process]:
        """Start FFmpeg process for recording."""
        os.makedirs(os.path.dirname(job.output_path), exist_ok=True)
        
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite
            "-rtsp_transport", "tcp",
            "-timeout", "10000000",  # 10s timeout
            "-i", job.rtsp_url,
            "-t", str(job.duration),
            "-c:v", "copy",
            "-c:a", "aac",
            "-movflags", "+faststart",  # Web-optimized
            job.tmp_path,
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _LOGGER.info("Started FFmpeg recording: %s (PID: %s)", job.camera_name, process.pid)
            return process
        except OSError as e:
            _LOGGER.error("Failed to start FFmpeg: %s", e)
            return None
    
    async def _generate_early_thumbnail(self, job: RecordingJob):
        """Generate early thumbnail 2s after recording start.
        
        This provides immediate visual feedback in the timeline
        before the full recording is complete.
        """
        await asyncio.sleep(2)  # Wait for some data to be recorded
        
        if job.state == RecordingState.FAILED:
            return
        
        early_thumb_path = job.output_path.replace(".mp4", "_preview.jpg")
        
        cmd = [
            "ffmpeg",
            "-y",
            "-rtsp_transport", "tcp",
            "-i", job.rtsp_url,
            "-frames:v", "1",
            "-q:v", "5",
            early_thumb_path,
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(process.wait(), timeout=10)
            
            if os.path.exists(early_thumb_path) and os.path.getsize(early_thumb_path) > 0:
                job.early_thumbnail_path = early_thumb_path
                _LOGGER.info("Early thumbnail ready: %s", early_thumb_path)
                
                if self.on_early_thumbnail:
                    self.on_early_thumbnail(job, early_thumb_path)
        except OSError as e:
            _LOGGER.warning("Early thumbnail failed: %s", e)
    
    async def _monitor_ffmpeg(self, job: RecordingJob):
        """Monitor FFmpeg process until completion."""
        if not job.process:
            return
        
        try:
            stdout, stderr = await job.process.communicate()
            
            if job.process.returncode != 0:
                stderr_text = stderr.decode('utf-8', errors='replace')[-500:] if stderr else ""
                _LOGGER.warning("FFmpeg exited with code %s: %s", job.process.returncode, stderr_text)
                job.error = f"FFmpeg error code {job.process.returncode}"
        except OSError as e:
            _LOGGER.error("FFmpeg monitoring failed: %s", e)
            job.error = str(e)
    
    async def _finalize_recording(self, job: RecordingJob) -> bool:
        """Rename .tmp to .mp4 with retry logic."""
        max_retries = 5
        
        for attempt in range(max_retries):
            if os.path.exists(job.tmp_path):
                size = os.path.getsize(job.tmp_path)
                
                if size > 0:
                    try:
                        os.rename(job.tmp_path, job.output_path)
                        _LOGGER.info("Recording finalized: %s (%d bytes)", job.output_path, size)
                        return True
                    except OSError as e:
                        if attempt < max_retries - 1:
                            _LOGGER.warning("Rename attempt %d failed: %s", attempt + 1, e)
                            await asyncio.sleep(1)
                        else:
                            _LOGGER.error("Rename failed after %d attempts", max_retries)
                            job.error = f"Rename failed: {e}"
                else:
                    _LOGGER.warning("Recording file empty, removing: %s", job.tmp_path)
                    os.remove(job.tmp_path)
                    job.error = "Recording file was empty"
                    return False
            else:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)  # File might still be writing
                    
        job.error = "Recording file not found"
        return False
    
    async def _generate_final_thumbnail(self, job: RecordingJob):
        """Generate thumbnail from the recorded video.
        
        Uses a frame from 25% into the video for better content representation.
        """
        if not os.path.exists(job.output_path):
            return
        
        thumb_path = job.final_thumbnail_path
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        
        # Extract frame from 25% into the video
        seek_time = max(1, job.duration // 4)
        
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(seek_time),
            "-i", job.output_path,
            "-frames:v", "1",
            "-q:v", "2",
            thumb_path,
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(process.wait(), timeout=30)
            
            if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                _LOGGER.info("Final thumbnail ready: %s", thumb_path)
                
                if self.on_final_thumbnail:
                    self.on_final_thumbnail(job, thumb_path)
            else:
                _LOGGER.warning("Final thumbnail generation failed")
        except OSError as e:
            _LOGGER.error("Thumbnail generation error: %s", e)
    
    async def _watchdog_loop(self):
        """Background task to cleanup stale recordings."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                stale_jobs = [
                    job for job in _active_jobs.values()
                    if job.is_overdue
                ]
                
                for job in stale_jobs:
                    _LOGGER.warning("Watchdog: Killing stale recording %s (elapsed: %.0fs, expected: %ds)",
                                   job.camera_name, job.elapsed_seconds, job.duration)
                    
                    if job.process and job.process.returncode is None:
                        job.process.terminate()
                        try:
                            await asyncio.wait_for(job.process.wait(), timeout=5)
                        except asyncio.TimeoutError:
                            job.process.kill()
                    
                    # Cleanup temp file
                    if os.path.exists(job.tmp_path):
                        try:
                            os.remove(job.tmp_path)
                        except OSError:
                            pass
                    
                    job.state = RecordingState.FAILED
                    job.error = "Watchdog timeout"
                    _active_jobs.pop(job.output_path, None)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Watchdog error: %s", e)


# Utility function to cleanup orphaned .tmp files
async def cleanup_stale_tmp_files(base_path: str, max_age_minutes: int = 120):
    """Remove .tmp files older than max_age_minutes.
    
    Run this on startup to clean up from crashes.
    """
    import glob
    
    now = time.time()
    max_age_seconds = max_age_minutes * 60
    cleaned = 0
    
    for tmp_file in glob.glob(os.path.join(base_path, "**", "*.tmp"), recursive=True):
        try:
            file_age = now - os.path.getmtime(tmp_file)
            if file_age > max_age_seconds:
                os.remove(tmp_file)
                cleaned += 1
                _LOGGER.info("Cleaned up stale temp file: %s (age: %.0f min)", tmp_file, file_age / 60)
        except OSError as e:
            _LOGGER.warning("Could not remove %s: %s", tmp_file, e)
    
    if cleaned:
        _LOGGER.info("Cleaned up %d stale temp files", cleaned)


# Timing analysis helper
def get_timing_stats() -> Dict[str, Any]:
    """Get timing statistics for active recordings."""
    return {
        "active_count": len(_active_jobs),
        "recordings": [
            {
                "camera": job.camera_name,
                "state": job.state.value,
                "elapsed": round(job.elapsed_seconds, 1),
                "duration": job.duration,
                "progress_pct": min(100, round(job.elapsed_seconds / job.duration * 100, 1)),
                "has_early_thumb": job.early_thumbnail_path is not None,
            }
            for job in _active_jobs.values()
        ]
    }
