#!/usr/bin/env python3
"""
Pre-Recording PoC Test Script

This script tests the pre-recording proof of concept on the Home Assistant server.
It can be run standalone to verify the implementation works correctly.

Usage:
    python test_prerecord_poc.py [camera_name]
    
    If no camera name is specified, it will test all configured cameras.
"""

import asyncio
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from pre_record_poc import PreRecordBuffer, PreRecordManager
except ImportError:
    print("Error: Cannot import pre_record_poc module")
    print("Make sure pre_record_poc.py is in the same directory")
    sys.exit(1)


# ============================================================================
# TEST CONFIGURATION
# ============================================================================

# Test cameras configuration
# These should match your actual camera setup
TEST_CAMERAS = {
    "testcam": {
        "rtsp_url": "rtsp://192.168.178.75:8554/testcam",
        "pre_record_seconds": 5,
    },
    "wohnzimmer": {
        "rtsp_url": "rtsp://192.168.178.75:8554/wohnzimmer",
        "pre_record_seconds": 5,
    },
    "flur": {
        "rtsp_url": "rtsp://192.168.178.75:8554/flur",
        "pre_record_seconds": 5,
    },
}

OUTPUT_DIR = Path("/config/www/rtsp_recordings/prerecord_tests")
BUFFER_FILL_TIME = 10  # Seconds to wait for buffer to fill
RECORD_DURATION = 10   # Live recording duration


# ============================================================================
# TEST FUNCTIONS
# ============================================================================

class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(title: str) -> None:
    """Print a formatted header."""
    print()
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {title}{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*60}{Colors.RESET}")
    print()


def print_step(step: int, message: str) -> None:
    """Print a step indicator."""
    print(f"{Colors.BLUE}[Step {step}]{Colors.RESET} {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"  {Colors.GREEN}✓{Colors.RESET} {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"  {Colors.RED}✗{Colors.RESET} {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"  {Colors.YELLOW}⚠{Colors.RESET} {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"  {Colors.CYAN}ℹ{Colors.RESET} {message}")


async def test_single_buffer(camera_name: str, config: dict) -> dict:
    """
    Test a single pre-record buffer.
    
    Returns:
        Dictionary with test results
    """
    results = {
        "camera": camera_name,
        "buffer_start": False,
        "segments_created": False,
        "recording_success": False,
        "output_file": None,
        "output_size": 0,
        "errors": []
    }
    
    rtsp_url = config.get("rtsp_url")
    pre_seconds = config.get("pre_record_seconds", 5)
    
    print_info(f"Testing camera: {camera_name}")
    print_info(f"RTSP URL: {rtsp_url}")
    print_info(f"Pre-record seconds: {pre_seconds}")
    print()
    
    # Create buffer
    buffer = PreRecordBuffer(
        rtsp_url=rtsp_url,
        camera_name=camera_name,
        buffer_seconds=pre_seconds + 5
    )
    
    try:
        # Start buffer
        print_step(1, "Starting pre-record buffer...")
        if await buffer.start():
            print_success("Buffer started successfully")
            results["buffer_start"] = True
        else:
            print_error("Failed to start buffer")
            results["errors"].append("Buffer start failed")
            return results
        
        # Wait for buffer to fill
        print_step(2, f"Waiting {BUFFER_FILL_TIME}s for buffer to fill...")
        for i in range(BUFFER_FILL_TIME):
            await asyncio.sleep(1)
            segments = await buffer.get_segments()
            print(f"    {i+1}s - {len(segments)} segments", end="\r")
        print()
        
        # Check segments
        segments = await buffer.get_segments()
        if segments:
            print_success(f"Buffer has {len(segments)} segments")
            results["segments_created"] = True
            
            # Show segment info
            total_size = sum(s.stat().st_size for s in segments)
            print_info(f"Total buffer size: {total_size / 1024:.1f} KB")
        else:
            print_error("No segments created")
            results["errors"].append("No segments created")
        
        # Test recording with pre-buffer
        print_step(3, f"Recording with pre-buffer ({pre_seconds}s pre + {RECORD_DURATION}s live)...")
        
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"prerecord_test_{camera_name}_{timestamp}.mp4"
        
        # Copy segments
        temp_dir = OUTPUT_DIR / f".temp_{camera_name}"
        temp_dir.mkdir(exist_ok=True)
        pre_segments = await buffer.copy_segments_to(temp_dir, pre_seconds)
        print_info(f"Copied {len(pre_segments)} pre-record segments")
        
        # Record live
        live_path = temp_dir / "live.mp4"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-rtsp_transport", "tcp", "-timeout", "5000000",
            "-i", rtsp_url, "-t", str(RECORD_DURATION),
            "-c", "copy", "-movflags", "+faststart",
            str(live_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        
        if process.returncode == 0 and live_path.exists():
            print_success(f"Live recording complete: {live_path.stat().st_size / 1024:.1f} KB")
        else:
            print_error(f"Live recording failed: {stderr.decode()}")
            results["errors"].append("Live recording failed")
            return results
        
        # Concatenate
        print_step(4, "Concatenating pre-buffer + live...")
        
        concat_file = temp_dir / "concat.txt"
        with open(concat_file, 'w') as f:
            for seg in pre_segments:
                f.write(f"file '{seg}'\n")
            f.write(f"file '{live_path}'\n")
        
        concat_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy", "-movflags", "+faststart",
            str(output_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *concat_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        
        if process.returncode == 0 and output_path.exists():
            output_size = output_path.stat().st_size
            print_success(f"Output file created: {output_path}")
            print_success(f"Output size: {output_size / 1024:.1f} KB")
            results["recording_success"] = True
            results["output_file"] = str(output_path)
            results["output_size"] = output_size
        else:
            print_error(f"Concatenation failed: {stderr.decode()}")
            results["errors"].append("Concatenation failed")
        
        # Cleanup temp
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Show buffer stats
        print_step(5, "Buffer statistics:")
        stats = buffer.stats
        print_info(f"Uptime: {stats['uptime_seconds']:.1f}s")
        print_info(f"Total segments created: {stats['total_segments']}")
        print_info(f"Restart count: {stats['restart_count']}")
        
    except Exception as e:
        print_error(f"Test failed with exception: {e}")
        results["errors"].append(str(e))
        
    finally:
        # Stop buffer
        print_step(6, "Stopping buffer...")
        await buffer.stop()
        print_success("Buffer stopped")
    
    return results


async def test_manager(cameras: dict) -> dict:
    """
    Test the PreRecordManager with multiple cameras.
    
    Returns:
        Dictionary with test results
    """
    results = {
        "manager_init": False,
        "cameras_tested": 0,
        "recordings_successful": 0,
        "errors": []
    }
    
    def on_complete(camera: str, path: str):
        print_success(f"Recording callback: {camera} -> {path}")
    
    manager = PreRecordManager(
        cameras_config=cameras,
        on_recording_complete=on_complete
    )
    
    try:
        print_step(1, "Initializing PreRecordManager...")
        if await manager.initialize():
            print_success(f"Manager initialized with {manager.active_buffers} buffers")
            results["manager_init"] = True
        else:
            print_error("Manager initialization failed")
            return results
        
        # Wait for buffers to fill
        print_step(2, f"Waiting {BUFFER_FILL_TIME}s for all buffers to fill...")
        await asyncio.sleep(BUFFER_FILL_TIME)
        
        # Show stats
        stats = manager.get_stats()
        print_info(f"Active buffers: {stats['active_buffers']}")
        for name, buf_stats in stats['buffers'].items():
            print_info(f"  {name}: {buf_stats['total_segments']} segments")
        
        # Test recording for each camera
        print_step(3, "Testing recordings...")
        
        for cam_name in cameras.keys():
            print()
            print_info(f"Testing {cam_name}...")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(OUTPUT_DIR / f"manager_test_{cam_name}_{timestamp}.mp4")
            
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            
            success = await manager.record_with_prebuffer(
                camera_name=cam_name,
                duration=RECORD_DURATION,
                output_path=output_path
            )
            
            results["cameras_tested"] += 1
            
            if success:
                print_success(f"{cam_name}: Recording successful")
                if Path(output_path).exists():
                    size_kb = Path(output_path).stat().st_size / 1024
                    print_success(f"{cam_name}: Output size: {size_kb:.1f} KB")
                results["recordings_successful"] += 1
            else:
                print_error(f"{cam_name}: Recording failed")
                results["errors"].append(f"{cam_name} recording failed")
        
        # Final stats
        print()
        print_step(4, "Final statistics:")
        stats = manager.get_stats()
        for name, buf_stats in stats['buffers'].items():
            print_info(f"{name}: {buf_stats['total_segments']} total segments, {buf_stats['restart_count']} restarts")
        
    except Exception as e:
        print_error(f"Manager test failed: {e}")
        results["errors"].append(str(e))
        
    finally:
        print()
        print_step(5, "Shutting down manager...")
        await manager.shutdown()
        print_success("Manager shutdown complete")
    
    return results


async def main():
    """Main test function."""
    print_header("Pre-Recording Proof of Concept Test")
    
    # Parse arguments
    camera_filter = sys.argv[1] if len(sys.argv) > 1 else None
    
    if camera_filter:
        if camera_filter not in TEST_CAMERAS:
            print_error(f"Unknown camera: {camera_filter}")
            print_info(f"Available cameras: {', '.join(TEST_CAMERAS.keys())}")
            sys.exit(1)
        cameras = {camera_filter: TEST_CAMERAS[camera_filter]}
        print_info(f"Testing single camera: {camera_filter}")
    else:
        cameras = TEST_CAMERAS
        print_info(f"Testing all cameras: {', '.join(cameras.keys())}")
    
    print()
    
    # Choose test mode
    if len(cameras) == 1:
        # Single camera - detailed test
        cam_name = list(cameras.keys())[0]
        cam_config = cameras[cam_name]
        
        print_header(f"Single Buffer Test: {cam_name}")
        results = await test_single_buffer(cam_name, cam_config)
        
    else:
        # Multiple cameras - manager test
        print_header("Manager Test (Multiple Cameras)")
        results = await test_manager(cameras)
    
    # Summary
    print()
    print_header("Test Summary")
    
    print(f"{Colors.BOLD}Results:{Colors.RESET}")
    print(json.dumps(results, indent=2, default=str))
    
    if results.get("errors"):
        print()
        print_warning(f"Errors encountered: {len(results['errors'])}")
        for err in results["errors"]:
            print_error(f"  {err}")
        return 1
    else:
        print()
        print_success("All tests passed!")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
