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


def _read_analysis_results(output_dir: str, limit: int = 50) -> list[dict[str, Any]]:
    """Read analysis results from output directory.
    
    Args:
        output_dir: Directory containing analysis_* subdirectories
        limit: Maximum number of results to return
        
    Returns:
        List of analysis result dicts, sorted by date (newest first)
    """
    if not os.path.exists(output_dir):
        return []
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
    return results[:limit]


def _find_analysis_for_video(output_dir: str, video_path: str) -> dict[str, Any] | None:
    """Find analysis result for a specific video file.
    
    Args:
        output_dir: Directory containing analysis results
        video_path: Path to the video file
        
    Returns:
        Analysis result dict or None if not found
    """
    for item in _read_analysis_results(output_dir, limit=200):
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
    for item in _read_analysis_results(output_dir, limit=10000):
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
    threshold: float = 0.6
) -> int:
    """Re-match all faces in existing analysis results against updated people database.
    
    This is called after adding/removing people or embeddings to update
    all historical analysis results with correct face matches.
    
    Args:
        output_dir: Directory containing analysis results
        people: Current people database list
        threshold: Minimum similarity threshold for matches
    
    Returns:
        The number of updated result files
    """
    if not os.path.exists(output_dir):
        return 0
    
    updated_count = 0
    
    def _process_analyses():
        nonlocal updated_count
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
                    updated_count += 1
                    
            except Exception:
                continue
        
        return updated_count
    
    await asyncio.to_thread(_process_analyses)
    return updated_count
