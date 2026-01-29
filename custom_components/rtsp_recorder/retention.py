"""Retention cleanup logic for RTSP Recorder.

This module handles automatic cleanup of old recordings and snapshots
based on configurable retention periods. Supports global settings and
per-camera overrides.
"""
import logging
import os
import time
from typing import Dict, Optional

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
