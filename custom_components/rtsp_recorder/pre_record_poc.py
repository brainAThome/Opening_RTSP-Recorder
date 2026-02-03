"""
Pre-Recording Proof of Concept for RTSP Recorder v1.2.0

This module provides configurable pre-recording functionality using HLS segments.
It allows recording N seconds BEFORE a motion event is triggered.

Author: RTSP Recorder Team
Version: 1.0.0-poc
Date: 2026-02-02

Usage:
    # Standalone test
    python pre_record_poc.py
    
    # Or import in your code
    from pre_record_poc import PreRecordBuffer, PreRecordManager
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_PRE_RECORD_SECONDS = 5
MIN_PRE_RECORD_SECONDS = 0
MAX_PRE_RECORD_SECONDS = 30
PRE_RECORD_SEGMENT_DURATION = 2  # HLS segment length in seconds
PRE_RECORD_BUFFER_DIR = "/tmp/rtsp_prerecord"
PRE_RECORD_HEALTH_CHECK_INTERVAL = 30  # Seconds between health checks
PRE_RECORD_RESTART_DELAY = 3  # Seconds to wait before restart on failure
PRE_RECORD_MAX_RESTART_ATTEMPTS = 5


# ============================================================================
# PRE-RECORD BUFFER CLASS
# ============================================================================

class PreRecordBuffer:
    """
    Manages a continuous HLS segment buffer for a single camera.
    
    This class creates a ring buffer of short video segments using FFmpeg's
    HLS muxer. When a recording is requested, these segments can be retrieved
    and concatenated with the live recording to include pre-event footage.
    
    Attributes:
        rtsp_url: The RTSP stream URL
        camera_name: Unique identifier for this camera
        buffer_seconds: How many seconds to keep in buffer
        segment_duration: Length of each HLS segment
    """
    
    def __init__(
        self,
        rtsp_url: str,
        camera_name: str,
        buffer_seconds: int = 10,
        segment_duration: int = PRE_RECORD_SEGMENT_DURATION,
        buffer_dir: str = PRE_RECORD_BUFFER_DIR
    ):
        """
        Initialize a new pre-record buffer.
        
        Args:
            rtsp_url: RTSP stream URL
            camera_name: Camera identifier (will be sanitized)
            buffer_seconds: Seconds to keep in buffer (default: 10)
            segment_duration: HLS segment duration (default: 2s)
            buffer_dir: Base directory for segment storage
        """
        self.rtsp_url = rtsp_url
        self.camera_name = self._sanitize_name(camera_name)
        self.buffer_seconds = buffer_seconds
        self.segment_duration = segment_duration
        self.segments_dir = Path(buffer_dir) / self.camera_name
        
        # Calculate how many segments to keep
        # Add 2 extra for safety margin
        self.max_segments = (buffer_seconds // segment_duration) + 2
        
        # Process management
        self._process: asyncio.subprocess.Process | None = None
        self._running = False
        self._lock = asyncio.Lock()
        self._monitor_task: asyncio.Task | None = None
        
        # Statistics
        self._start_time: datetime | None = None
        self._restart_count = 0
        self._last_segment_time: datetime | None = None
        self._total_segments_created = 0
    
    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize camera name for filesystem use."""
        # Replace problematic characters
        sanitized = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return sanitized.lower()
    
    @property
    def is_running(self) -> bool:
        """Check if buffer is currently running."""
        return self._running and self._process is not None
    
    @property
    def uptime_seconds(self) -> float:
        """Get buffer uptime in seconds."""
        if self._start_time:
            return (datetime.now() - self._start_time).total_seconds()
        return 0.0
    
    @property
    def stats(self) -> dict:
        """Get buffer statistics."""
        return {
            "camera_name": self.camera_name,
            "running": self.is_running,
            "uptime_seconds": self.uptime_seconds,
            "restart_count": self._restart_count,
            "total_segments": self._total_segments_created,
            "buffer_seconds": self.buffer_seconds,
            "segment_duration": self.segment_duration,
            "max_segments": self.max_segments,
        }
    
    async def start(self) -> bool:
        """
        Start the continuous HLS recording process.
        
        Returns:
            True if successfully started, False otherwise.
        """
        async with self._lock:
            if self._running:
                _LOGGER.warning(f"Buffer for {self.camera_name} already running")
                return True
            
            # Create segments directory
            self.segments_dir.mkdir(parents=True, exist_ok=True)
            
            # Clean old segments
            await self._cleanup_segments()
            
            # Build FFmpeg command
            cmd = self._build_ffmpeg_command()
            _LOGGER.info(f"Starting pre-record buffer for {self.camera_name}")
            _LOGGER.debug(f"FFmpeg command: {' '.join(cmd)}")
            
            try:
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE
                )
                self._running = True
                self._start_time = datetime.now()
                
                # Start background monitor
                self._monitor_task = asyncio.create_task(
                    self._monitor_process(),
                    name=f"prerecord_monitor_{self.camera_name}"
                )
                
                _LOGGER.info(
                    f"Pre-record buffer started for {self.camera_name} "
                    f"(buffer={self.buffer_seconds}s, segments={self.max_segments})"
                )
                return True
                
            except FileNotFoundError:
                _LOGGER.error("FFmpeg not found. Please install FFmpeg.")
                return False
            except OSError as e:
                _LOGGER.error(f"Failed to start pre-record buffer for {self.camera_name}: {e}")
                return False
    
    def _build_ffmpeg_command(self) -> list[str]:
        """Build FFmpeg HLS command."""
        playlist_path = self.segments_dir / "playlist.m3u8"
        segment_pattern = self.segments_dir / "seg%05d.ts"
        
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            
            # Input options
            "-rtsp_transport", "tcp",
            "-timeout", "5000000",  # 5 second timeout
            "-i", self.rtsp_url,
            
            # Output options - copy codec (no re-encoding)
            "-c", "copy",
            
            # HLS specific options
            "-f", "hls",
            "-hls_time", str(self.segment_duration),
            "-hls_list_size", str(self.max_segments),
            "-hls_flags", "delete_segments+append_list",
            "-hls_segment_filename", str(segment_pattern),
            
            str(playlist_path)
        ]
        
        return cmd
    
    async def _monitor_process(self) -> None:
        """Monitor FFmpeg process and restart if needed."""
        while self._running:
            try:
                if self._process is None:
                    break
                
                # Check if process is still running
                return_code = self._process.returncode
                
                if return_code is not None:
                    # Process has exited
                    _LOGGER.warning(
                        f"Pre-record buffer for {self.camera_name} "
                        f"exited with code {return_code}"
                    )
                    
                    if self._running:
                        # Attempt restart
                        await self._attempt_restart()
                    break
                
                # Check for new segments (health check)
                segments = await self.get_segments()
                if segments:
                    newest = max(segments, key=lambda p: p.stat().st_mtime)
                    mtime = datetime.fromtimestamp(newest.stat().st_mtime)
                    
                    if self._last_segment_time != mtime:
                        self._last_segment_time = mtime
                        self._total_segments_created += 1
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error(f"Error in monitor for {self.camera_name}: {e}")
                await asyncio.sleep(5)
    
    async def _attempt_restart(self) -> None:
        """Attempt to restart the buffer after failure."""
        if self._restart_count >= PRE_RECORD_MAX_RESTART_ATTEMPTS:
            _LOGGER.error(
                f"Max restart attempts ({PRE_RECORD_MAX_RESTART_ATTEMPTS}) "
                f"reached for {self.camera_name}. Giving up."
            )
            self._running = False
            return
        
        self._restart_count += 1
        _LOGGER.info(
            f"Restarting pre-record buffer for {self.camera_name} "
            f"(attempt {self._restart_count})"
        )
        
        await asyncio.sleep(PRE_RECORD_RESTART_DELAY)
        
        # Clean up old process
        self._process = None
        
        # Restart
        cmd = self._build_ffmpeg_command()
        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            _LOGGER.info(f"Successfully restarted buffer for {self.camera_name}")
        except OSError as e:
            _LOGGER.error(f"Failed to restart buffer for {self.camera_name}: {e}")
    
    async def get_segments(self, max_seconds: int | None = None) -> list[Path]:
        """
        Get current segment files.
        
        Args:
            max_seconds: Optional limit on how many seconds of segments to return.
                        If None, returns all available segments.
        
        Returns:
            List of Path objects to segment files, sorted by modification time.
        """
        if not self.segments_dir.exists():
            return []
        
        segments = sorted(
            self.segments_dir.glob("seg*.ts"),
            key=lambda p: p.stat().st_mtime
        )
        
        if max_seconds and segments:
            # Calculate how many segments we need
            needed = (max_seconds // self.segment_duration) + 1
            segments = segments[-needed:]
        
        return segments
    
    async def copy_segments_to(
        self,
        target_dir: Path,
        max_seconds: int | None = None
    ) -> list[Path]:
        """
        Copy current segments to a target directory.
        
        This is useful when you want to preserve segments before they get
        rotated out of the buffer.
        
        Args:
            target_dir: Directory to copy segments to
            max_seconds: Optional limit on how many seconds to copy
        
        Returns:
            List of paths to copied segment files
        """
        segments = await self.get_segments(max_seconds)
        
        if not segments:
            return []
        
        target_dir.mkdir(parents=True, exist_ok=True)
        copied = []
        
        for seg in segments:
            target_path = target_dir / seg.name
            shutil.copy2(seg, target_path)
            copied.append(target_path)
        
        return copied
    
    async def _cleanup_segments(self) -> None:
        """Remove all segment files from buffer directory."""
        if self.segments_dir.exists():
            for f in self.segments_dir.glob("seg*.ts"):
                f.unlink(missing_ok=True)
            
            playlist = self.segments_dir / "playlist.m3u8"
            playlist.unlink(missing_ok=True)
    
    async def stop(self) -> None:
        """Stop the buffer process and cleanup."""
        _LOGGER.info(f"Stopping pre-record buffer for {self.camera_name}")
        
        async with self._lock:
            self._running = False
            
            # Cancel monitor task
            if self._monitor_task:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
                self._monitor_task = None
            
            # Stop FFmpeg process
            if self._process:
                try:
                    self._process.terminate()
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    _LOGGER.warning(f"Force killing buffer for {self.camera_name}")
                    self._process.kill()
                except OSError as e:
                    _LOGGER.error(f"Error stopping buffer for {self.camera_name}: {e}")
                finally:
                    self._process = None
            
            # Cleanup segments
            await self._cleanup_segments()
            
            _LOGGER.info(f"Pre-record buffer stopped for {self.camera_name}")


# ============================================================================
# PRE-RECORD MANAGER CLASS
# ============================================================================

class PreRecordManager:
    """
    Manages pre-record buffers for multiple cameras.
    
    This class coordinates multiple PreRecordBuffer instances and provides
    the main interface for recording with pre-buffer included.
    
    Attributes:
        buffers: Dictionary mapping camera names to their buffer instances
    """
    
    def __init__(
        self,
        cameras_config: dict[str, dict],
        on_recording_complete: Callable[[str, str], Any] | None = None
    ):
        """
        Initialize the pre-record manager.
        
        Args:
            cameras_config: Dictionary of camera configurations
                {
                    "camera_name": {
                        "rtsp_url": "rtsp://...",
                        "pre_record_seconds": 5,
                        ...
                    }
                }
            on_recording_complete: Optional callback when recording finishes
        """
        self.cameras_config = cameras_config
        self.on_recording_complete = on_recording_complete
        self.buffers: dict[str, PreRecordBuffer] = {}
        self._initialized = False
        self._health_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
    
    @property
    def is_initialized(self) -> bool:
        """Check if manager is initialized."""
        return self._initialized
    
    @property
    def active_buffers(self) -> int:
        """Get count of active buffers."""
        return sum(1 for b in self.buffers.values() if b.is_running)
    
    def get_stats(self) -> dict:
        """Get statistics for all buffers."""
        return {
            "initialized": self._initialized,
            "total_buffers": len(self.buffers),
            "active_buffers": self.active_buffers,
            "buffers": {
                name: buffer.stats
                for name, buffer in self.buffers.items()
            }
        }
    
    async def initialize(self) -> bool:
        """
        Initialize pre-record buffers for all configured cameras.
        
        Returns:
            True if at least one buffer was started successfully.
        """
        if self._initialized:
            _LOGGER.warning("PreRecordManager already initialized")
            return True
        
        _LOGGER.info("Initializing PreRecordManager...")
        
        started_count = 0
        
        for cam_name, cam_config in self.cameras_config.items():
            pre_seconds = cam_config.get("pre_record_seconds", 0)
            
            if pre_seconds <= 0:
                _LOGGER.debug(f"Pre-recording disabled for {cam_name}")
                continue
            
            rtsp_url = cam_config.get("rtsp_url")
            if not rtsp_url:
                _LOGGER.warning(f"No RTSP URL for {cam_name}, skipping pre-record")
                continue
            
            # Create buffer with extra margin
            buffer = PreRecordBuffer(
                rtsp_url=rtsp_url,
                camera_name=cam_name,
                buffer_seconds=pre_seconds + 5  # Extra margin for safety
            )
            
            if await buffer.start():
                self.buffers[cam_name] = buffer
                started_count += 1
                _LOGGER.info(
                    f"✓ Pre-record buffer started: {cam_name} ({pre_seconds}s)"
                )
            else:
                _LOGGER.error(f"✗ Failed to start pre-record buffer: {cam_name}")
        
        # Start health check task
        if started_count > 0:
            self._health_task = asyncio.create_task(
                self._health_check_loop(),
                name="prerecord_health_check"
            )
        
        self._initialized = True
        _LOGGER.info(
            f"PreRecordManager initialized: {started_count}/{len(self.cameras_config)} buffers active"
        )
        
        return started_count > 0
    
    async def _health_check_loop(self) -> None:
        """Periodic health check for all buffers."""
        while True:
            try:
                await asyncio.sleep(PRE_RECORD_HEALTH_CHECK_INTERVAL)
                
                for name, buffer in self.buffers.items():
                    if not buffer.is_running:
                        _LOGGER.warning(f"Buffer {name} not running, attempting restart")
                        await buffer.start()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error(f"Error in health check: {e}")
    
    async def record_with_prebuffer(
        self,
        camera_name: str,
        duration: int,
        output_path: str,
        pre_seconds: int | None = None
    ) -> bool:
        """
        Record video with pre-buffer included.
        
        This method:
        1. Copies current buffer segments
        2. Records live video for the specified duration
        3. Concatenates pre-buffer + live into final output
        
        Args:
            camera_name: Name of the camera to record from
            duration: Recording duration in seconds
            output_path: Path for the output file
            pre_seconds: How many seconds of pre-buffer to include
                        (defaults to camera config)
        
        Returns:
            True if recording was successful, False otherwise.
        """
        async with self._lock:
            buffer = self.buffers.get(camera_name)
            cam_config = self.cameras_config.get(camera_name, {})
            
            if pre_seconds is None:
                pre_seconds = cam_config.get("pre_record_seconds", 5)
            
            # If no buffer or not running, fall back to normal recording
            if not buffer or not buffer.is_running:
                _LOGGER.warning(
                    f"No active pre-record buffer for {camera_name}, "
                    "falling back to normal recording"
                )
                return await self._record_normal(
                    cam_config.get("rtsp_url", ""),
                    duration,
                    output_path
                )
            
            _LOGGER.info(
                f"Starting pre-record capture for {camera_name}: "
                f"pre={pre_seconds}s, live={duration}s"
            )
            
            try:
                output_file = Path(output_path)
                temp_dir = output_file.parent / f".prerecord_{uuid.uuid4().hex}"
                temp_dir.mkdir(parents=True, exist_ok=True)
                
                # 1. Copy pre-record segments
                _LOGGER.debug(f"Copying pre-record segments for {camera_name}")
                pre_segments = await buffer.copy_segments_to(temp_dir, pre_seconds)
                
                if not pre_segments:
                    _LOGGER.warning(f"No pre-record segments available for {camera_name}")
                
                # 2. Record live portion
                live_path = temp_dir / "live.mp4"
                _LOGGER.debug(f"Recording live portion for {camera_name} ({duration}s)")
                
                live_success = await self._record_live(
                    buffer.rtsp_url,
                    duration,
                    str(live_path)
                )
                
                if not live_success:
                    _LOGGER.error(f"Live recording failed for {camera_name}")
                    return False
                
                # 3. Concatenate pre + live
                _LOGGER.debug(f"Concatenating segments for {camera_name}")
                concat_success = await self._concat_segments(
                    pre_segments,
                    live_path,
                    output_path
                )
                
                if concat_success:
                    _LOGGER.info(
                        f"✓ Pre-record capture complete: {camera_name} -> {output_path}"
                    )
                    
                    if self.on_recording_complete:
                        self.on_recording_complete(camera_name, output_path)
                
                return concat_success
                
            except OSError as e:
                _LOGGER.error(f"Pre-record capture failed for {camera_name}: {e}")
                return False
                
            finally:
                # Cleanup temp directory
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
    
    async def _record_live(
        self,
        rtsp_url: str,
        duration: int,
        output_path: str
    ) -> bool:
        """Record live video from RTSP stream."""
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-rtsp_transport", "tcp",
            "-timeout", "5000000",
            "-i", rtsp_url,
            "-t", str(duration),
            "-c", "copy",
            "-movflags", "+faststart",
            output_path
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=duration + 30  # Add 30s buffer
            )
            
            if process.returncode != 0:
                _LOGGER.error(f"Live recording failed: {stderr.decode()}")
                return False
            
            return Path(output_path).exists()
            
        except asyncio.TimeoutError:
            _LOGGER.error("Live recording timed out")
            return False
        except OSError as e:
            _LOGGER.error(f"Live recording error: {e}")
            return False
    
    async def _record_normal(
        self,
        rtsp_url: str,
        duration: int,
        output_path: str
    ) -> bool:
        """Normal recording without pre-buffer (fallback)."""
        if not rtsp_url:
            _LOGGER.error("No RTSP URL for normal recording")
            return False
        
        return await self._record_live(rtsp_url, duration, output_path)
    
    async def _concat_segments(
        self,
        segments: list[Path],
        live_path: Path,
        output_path: str
    ) -> bool:
        """Concatenate HLS segments with live recording."""
        if not segments and not live_path.exists():
            _LOGGER.error("No segments and no live recording to concatenate")
            return False
        
        # If no segments, just copy live
        if not segments:
            shutil.copy2(live_path, output_path)
            return True
        
        # If no live, just concat segments
        if not live_path.exists():
            segments_only = segments
        else:
            segments_only = None
        
        # Create concat list file
        concat_file = Path(output_path).parent / f".concat_{uuid.uuid4().hex}.txt"
        
        try:
            with open(concat_file, 'w') as f:
                for seg in segments:
                    # Use proper escaping for Windows paths
                    seg_path = str(seg).replace('\\', '/')
                    f.write(f"file '{seg_path}'\n")
                
                if live_path.exists():
                    live_path_str = str(live_path).replace('\\', '/')
                    f.write(f"file '{live_path_str}'\n")
            
            # FFmpeg concat
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "warning",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                "-movflags", "+faststart",
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            
            if process.returncode != 0:
                _LOGGER.error(f"Concat failed: {stderr.decode()}")
                return False
            
            return Path(output_path).exists()
            
        except OSError as e:
            _LOGGER.error(f"Concat error: {e}")
            return False
            
        finally:
            concat_file.unlink(missing_ok=True)
    
    async def shutdown(self) -> None:
        """Stop all buffers and cleanup."""
        _LOGGER.info("Shutting down PreRecordManager...")
        
        # Cancel health check
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None
        
        # Stop all buffers
        for name, buffer in self.buffers.items():
            await buffer.stop()
        
        self.buffers.clear()
        self._initialized = False
        
        _LOGGER.info("PreRecordManager shutdown complete")


# ============================================================================
# STANDALONE TEST / DEMO
# ============================================================================

async def demo():
    """
    Demo/test function to verify pre-recording functionality.
    
    This can be run standalone to test the implementation.
    """
    print("=" * 60)
    print("  Pre-Recording Proof of Concept Demo")
    print("=" * 60)
    print()
    
    # Demo configuration
    # Replace with your actual RTSP URL for testing
    DEMO_RTSP_URL = os.environ.get(
        "DEMO_RTSP_URL",
        "rtsp://admin:password@192.168.1.100:554/stream"
    )
    
    cameras_config = {
        "test_camera": {
            "rtsp_url": DEMO_RTSP_URL,
            "pre_record_seconds": 5,
        }
    }
    
    # Callback when recording completes
    def on_complete(camera: str, path: str):
        print(f"\n✓ Recording complete: {camera} -> {path}")
        print(f"  File size: {Path(path).stat().st_size / 1024:.1f} KB")
    
    # Create manager
    manager = PreRecordManager(
        cameras_config=cameras_config,
        on_recording_complete=on_complete
    )
    
    try:
        # Initialize
        print("1. Initializing pre-record buffers...")
        success = await manager.initialize()
        
        if not success:
            print("   ✗ Failed to initialize. Check RTSP URL and FFmpeg.")
            print(f"   RTSP URL: {DEMO_RTSP_URL}")
            return
        
        print("   ✓ Buffers initialized")
        print()
        
        # Wait for buffer to fill
        print("2. Waiting for buffer to fill (10 seconds)...")
        for i in range(10, 0, -1):
            print(f"   {i}...", end=" ", flush=True)
            await asyncio.sleep(1)
        print()
        print()
        
        # Show stats
        print("3. Buffer statistics:")
        stats = manager.get_stats()
        for name, buffer_stats in stats["buffers"].items():
            print(f"   {name}:")
            print(f"     Running: {buffer_stats['running']}")
            print(f"     Uptime: {buffer_stats['uptime_seconds']:.1f}s")
            print(f"     Segments: {buffer_stats['total_segments']}")
        print()
        
        # Simulate motion event - trigger recording
        print("4. Simulating motion event...")
        output_path = "/tmp/prerecord_test_output.mp4"
        
        success = await manager.record_with_prebuffer(
            camera_name="test_camera",
            duration=10,  # 10 second live recording
            output_path=output_path,
            pre_seconds=5  # Include 5 seconds before event
        )
        
        if success:
            print(f"   ✓ Recording saved: {output_path}")
            if Path(output_path).exists():
                size_kb = Path(output_path).stat().st_size / 1024
                print(f"   ✓ File size: {size_kb:.1f} KB")
                print(f"   ✓ Expected duration: ~15 seconds (5s pre + 10s live)")
        else:
            print("   ✗ Recording failed")
        print()
        
        # Final stats
        print("5. Final statistics:")
        stats = manager.get_stats()
        print(f"   Active buffers: {stats['active_buffers']}")
        for name, buffer_stats in stats["buffers"].items():
            print(f"   {name}: {buffer_stats['total_segments']} segments created")
        
    finally:
        # Cleanup
        print()
        print("6. Shutting down...")
        await manager.shutdown()
        print("   ✓ Shutdown complete")
    
    print()
    print("=" * 60)
    print("  Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    # Run demo
    print()
    print("Pre-Recording PoC - Standalone Test")
    print()
    print("Set DEMO_RTSP_URL environment variable to test with your camera:")
    print("  export DEMO_RTSP_URL='rtsp://user:pass@ip:554/stream'")
    print()
    
    asyncio.run(demo())
