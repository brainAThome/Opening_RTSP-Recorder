"""Analysis helpers for RTSP Recorder Integration.

This module contains utility functions for analysis results:
- Reading and parsing analysis results
- Building analysis index
- Summarizing analysis statistics
- Re-matching faces after people DB updates
"""
import asyncio
import json
import os
from typing import Any

from .face_matching import _match_face_simple


def _read_analysis_results(output_dir: str, limit: int = 50, page: int = 1, per_page: int = 0) -> dict[str, Any]:
    """Read analysis results from output directory with pagination support.
    
    Args:
        output_dir: Directory containing analysis_* subdirectories
        limit: Maximum number of results to return (legacy, ignored if per_page > 0)
        page: Page number (1-indexed)
        per_page: Results per page (0 = no pagination, use limit)
        
    Returns:
        Dict with items, total, page, per_page, total_pages keys
    """
    if not os.path.exists(output_dir):
        return {"items": [], "total": 0, "page": 1, "per_page": per_page or limit, "total_pages": 0}
    
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
    total = len(results)
    
    # Pagination mode
    if per_page > 0:
        total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        start = (page - 1) * per_page
        end = start + per_page
        items = results[start:end]
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }
    
    # Legacy mode (backward compatible)
    return {
        "items": results[:limit],
        "total": total,
        "page": 1,
        "per_page": limit,
        "total_pages": 1
    }


def _read_analysis_results_legacy(output_dir: str, limit: int = 50) -> list[dict[str, Any]]:
    """Legacy function for backward compatibility.
    
    Args:
        output_dir: Directory containing analysis_* subdirectories
        limit: Maximum number of results to return
        
    Returns:
        List of analysis result dicts, sorted by date (newest first)
    """
    result = _read_analysis_results(output_dir, limit=limit)
    return result.get("items", [])


def _find_analysis_for_video(output_dir: str, video_path: str) -> dict[str, Any] | None:
    """Find analysis result for a specific video file.
    
    Args:
        output_dir: Directory containing analysis results
        video_path: Path to the video file
        
    Returns:
        Analysis result dict or None if not found
    """
    result = _read_analysis_results(output_dir, limit=200)
    for item in result.get("items", []):
        if item.get("video_path") == video_path:
            return item
    return None


def _build_analysis_index(output_dir: str) -> set[str]:
    """Build a set of all video paths that have been analyzed.
    
    Args:
        output_dir: Directory containing analysis results
        
    Returns:
        Set of video file paths
    """
    existing = set()
    result = _read_analysis_results(output_dir, limit=10000)
    for item in result.get("items", []):
        path = item.get("video_path")
        if path:
            existing.add(path)
    return existing


def _summarize_analysis(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Create summary statistics from analysis results.
    
    Args:
        items: List of analysis result dicts
        
    Returns:
        Summary dict with totals and averages
    """
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


async def _update_all_face_matches(
    output_dir: str, 
    people: list[dict[str, Any]], 
    threshold: float = 0.6,
    max_analyses: int = 100
) -> int:
    """Re-match all faces in existing analysis results against updated people database.
    
    This is called after adding/removing people or embeddings to update
    historical analysis results with correct face matches.
    
    Optimizations:
    - Only processes the most recent N analyses (configurable via max_analyses)
    - Uses parallel file I/O for better performance
    - Skips analyses with no faces
    
    Args:
        output_dir: Directory containing analysis results
        people: Current people database list
        threshold: Minimum similarity threshold for matches
        max_analyses: Maximum number of analysis files to process (newest first)
    
    Returns:
        The number of updated result files
    """
    if not os.path.exists(output_dir):
        return 0
    
    # Collect analysis directories with modification times
    def _get_analysis_dirs():
        dirs = []
        for name in os.listdir(output_dir):
            if not name.startswith("analysis_"):
                continue
            job_dir = os.path.join(output_dir, name)
            result_path = os.path.join(job_dir, "result.json")
            if os.path.exists(result_path):
                try:
                    mtime = os.path.getmtime(result_path)
                    dirs.append((result_path, mtime))
                except OSError:
                    continue
        # Sort by modification time (newest first) and limit
        dirs.sort(key=lambda x: x[1], reverse=True)
        return [d[0] for d in dirs[:max_analyses]]
    
    analysis_files = await asyncio.to_thread(_get_analysis_dirs)
    
    if not analysis_files:
        return 0
    
    updated_count = 0
    
    def _process_single_file(result_path: str) -> bool:
        """Process a single analysis file. Returns True if modified."""
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
                return True
            return False
                
        except Exception:
            return False
    
    # Process files (one at a time to avoid disk thrashing)
    for result_path in analysis_files:
        was_modified = await asyncio.to_thread(_process_single_file, result_path)
        if was_modified:
            updated_count += 1
    
    return updated_count
