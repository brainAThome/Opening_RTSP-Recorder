"""Retention cleanup logic for RTSP Recorder.

This module handles automatic cleanup of old recordings, snapshots,
and analysis data based on configurable retention periods. Supports 
global settings and per-camera overrides.

v1.1.0k: Added cleanup_analysis_data() for analysis folder cleanup.
"""
import logging
import os
import re
import shutil
import time
from typing import Dict, Optional, Tuple

_LOGGER = logging.getLogger(__name__)


def parse_retention_map(config_str: Optional[str]) -> Dict[str, int]:
    """Parse retention configuration string into a dictionary.
    
    Args:
        config_str: String in format 'Folder:Hours; Folder2:Hours'
    
    Returns:
        Dictionary mapping folder names to retention hours.
        Empty dict if config_str is None or empty.
    
    Example:
        >>> parse_retention_map("Camera1:48; Camera2:72")
        {'Camera1': 48, 'Camera2': 72}
    """
    mapping: Dict[str, int] = {}
    if not config_str:
        return mapping
    
    parts = config_str.split(";")
    for part in parts:
        if ":" in part:
            try:
                folder, hours = part.split(":")
                folder = folder.strip()
                hours = int(hours.strip())
                mapping[folder] = hours
            except ValueError:
                _LOGGER.warning(f"Invalid retention rule: {part}")
    return mapping


def cleanup_recordings(
    base_path: str,
    global_days: int,
    global_hours: int = 0,
    override_map: Optional[Dict[str, int]] = None
) -> None:
    """Delete files older than the retention period.
    
    Walks the directory tree and removes files that exceed their
    retention period. Supports per-folder overrides for cameras
    with different retention requirements.
    
    Args:
        base_path: Root directory containing recordings
        global_days: Default retention period in days
        global_hours: Additional hours to add to global retention
        override_map: Optional dict mapping folder names to retention hours
    
    Note:
        Override map takes precedence over global settings.
        Files in folders matching override keys use the specified hours.
    """
    
    # Calculate global cutoff
    global_seconds = (global_days * 86400) + (global_hours * 3600)
    global_cutoff = time.time() - global_seconds
    
    _LOGGER.info(f"Starting cleanup. Global: {global_days}d {global_hours}h. Overrides: {override_map}")

    if not os.path.exists(base_path):
        _LOGGER.warning(f"Storage path not found: {base_path}")
        return

    count_deleted = 0
    size_freed = 0

    # Walk the directory tree
    for root, dirs, files in os.walk(base_path):
        
        # Determine retention policy for this execution context (folder)
        # simplistic check: is one of the override keys in the path?
        # Better: Get relative path and check first component
        rel_path = os.path.relpath(root, base_path)
        
        # Default to global
        current_cutoff = global_cutoff
        
        if rel_path != ".":
            # Extract top-level folder name (Camera Name)
            # normalized path components
            path_parts = rel_path.split(os.sep)
            top_folder = path_parts[0]
            
            if override_map and top_folder in override_map:
                override_hours = override_map[top_folder]
                override_seconds = override_hours * 3600
                current_cutoff = time.time() - override_seconds
                # limit logging spam
                # _LOGGER.debug(f"Using override for {top_folder}: {override_hours}h")

        for name in files:
            file_path = os.path.join(root, name)
            try:
                stats = os.stat(file_path)
                if stats.st_mtime < current_cutoff:
                    file_size = stats.st_size
                    os.remove(file_path)
                    count_deleted += 1
                    size_freed += file_size
                    _LOGGER.debug(f"Deleted old recording: {file_path}")
            except Exception as e:
                _LOGGER.error(f"Error deleting {file_path}: {e}")

    if count_deleted > 0:
        mb_freed = size_freed / (1024 * 1024)
        _LOGGER.info(f"Cleanup Finished: Deleted {count_deleted} files, freed {mb_freed:.2f} MB")
    else:
        _LOGGER.debug("Cleanup completed: No files exceeded retention period")


def cleanup_analysis_data(
    storage_path: str,
    global_days: int,
    global_hours: int = 0,
) -> Tuple[int, float]:
    """Delete analysis folders older than the retention period.
    
    Analysis folders are named like 'analysis_YYYYMMDD_HHMMSS' and contain
    result.json, frames/, and annotated/ subdirectories.
    
    Args:
        storage_path: Root directory containing camera folders with _analysis subdirs
        global_days: Default retention period in days
        global_hours: Additional hours to add to global retention
        
    Returns:
        Tuple of (folders_deleted, mb_freed)
    """
    global_seconds = (global_days * 86400) + (global_hours * 3600)
    global_cutoff = time.time() - global_seconds
    
    folders_deleted = 0
    size_freed = 0
    
    if not os.path.exists(storage_path):
        return 0, 0.0
    
    # Find all _analysis directories
    for camera_folder in os.listdir(storage_path):
        camera_path = os.path.join(storage_path, camera_folder)
        if not os.path.isdir(camera_path):
            continue
            
        analysis_path = os.path.join(camera_path, "_analysis")
        if not os.path.exists(analysis_path):
            continue
            
        # Process analysis_YYYYMMDD_HHMMSS folders
        try:
            for analysis_folder in os.listdir(analysis_path):
                if not analysis_folder.startswith("analysis_"):
                    continue
                    
                folder_path = os.path.join(analysis_path, analysis_folder)
                if not os.path.isdir(folder_path):
                    continue
                
                # Extract date from folder name: analysis_20260131_164147
                match = re.match(r'analysis_(\d{8})_(\d{6})', analysis_folder)
                if not match:
                    continue
                    
                # Use folder modification time as fallback
                try:
                    folder_mtime = os.stat(folder_path).st_mtime
                except Exception:
                    continue
                    
                if folder_mtime < global_cutoff:
                    # Calculate folder size before deletion
                    folder_size = 0
                    for dirpath, dirnames, filenames in os.walk(folder_path):
                        for f in filenames:
                            fp = os.path.join(dirpath, f)
                            try:
                                folder_size += os.path.getsize(fp)
                            except Exception:
                                pass
                    
                    try:
                        shutil.rmtree(folder_path)
                        folders_deleted += 1
                        size_freed += folder_size
                        _LOGGER.debug(f"Deleted old analysis: {folder_path}")
                    except Exception as e:
                        _LOGGER.error(f"Error deleting analysis folder {folder_path}: {e}")
                        
        except Exception as e:
            _LOGGER.error(f"Error processing analysis in {camera_path}: {e}")
    
    if folders_deleted > 0:
        mb_freed = size_freed / (1024 * 1024)
        _LOGGER.info(f"Analysis cleanup: Deleted {folders_deleted} folders, freed {mb_freed:.2f} MB")
    
    return folders_deleted, size_freed / (1024 * 1024)


def get_analysis_folder_for_video(video_path: str, storage_path: str) -> Optional[str]:
    """Get the analysis folder path for a given video file.
    
    Args:
        video_path: Full path to the video file
        storage_path: Root storage path for recordings
        
    Returns:
        Path to the analysis folder if it exists, None otherwise
        
    Example:
        video: /media/rtsp_recordings/Camera1/Camera1_20260131_164147.mp4
        returns: /media/rtsp_recordings/Camera1/_analysis/analysis_20260131_164147
    """
    if not video_path or not os.path.exists(video_path):
        return None
        
    # Extract camera folder and timestamp from video path
    video_dir = os.path.dirname(video_path)
    video_name = os.path.basename(video_path)
    
    # Extract timestamp: CameraName_YYYYMMDD_HHMMSS.mp4
    match = re.search(r'(\d{8}_\d{6})\.mp4$', video_name)
    if not match:
        return None
        
    timestamp = match.group(1)
    analysis_folder = f"analysis_{timestamp}"
    analysis_path = os.path.join(video_dir, "_analysis", analysis_folder)
    
    if os.path.exists(analysis_path):
        return analysis_path
    
    return None


def delete_analysis_for_video(video_path: str, storage_path: str) -> bool:
    """Delete the analysis folder associated with a video file.
    
    Args:
        video_path: Full path to the video file
        storage_path: Root storage path for recordings
        
    Returns:
        True if analysis folder was deleted, False otherwise
    """
    analysis_path = get_analysis_folder_for_video(video_path, storage_path)
    
    if analysis_path and os.path.exists(analysis_path):
        try:
            shutil.rmtree(analysis_path)
            _LOGGER.info(f"Deleted analysis folder: {analysis_path}")
            return True
        except Exception as e:
            _LOGGER.error(f"Error deleting analysis folder {analysis_path}: {e}")
            
    return False
