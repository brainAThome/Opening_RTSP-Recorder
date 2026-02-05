"""Video Analysis Module for RTSP Recorder Integration.

This module provides AI-powered video analysis capabilities:
- Object detection using TFLite models (MobileDet, SSD MobileNet)
- Face detection and embedding extraction
- Person matching against trained faces database
- Frame extraction and annotation
- Support for Coral EdgeTPU acceleration

Key Features:
- Async processing with non-blocking I/O
- Memory-efficient thumbnail generation
- Cosine similarity matching for face recognition
- Centroid-based fast matching algorithm
- Negative sample filtering to prevent false positives

Memory Management:
- MAX_FACES_WITH_THUMBS: Limits embedded thumbnails per analysis
- MAX_THUMB_SIZE: Constrains thumbnail dimensions
- THUMB_JPEG_QUALITY: Controls compression level

Version: 1.1.1
Changes in 1.1.1:
- Fixed blocking I/O calls (os.listdir, shutil.rmtree) with run_in_executor
- Moved shutil import to module level
"""
import asyncio
import json
import logging
import os
import shutil
import time
import urllib.request
import aiohttp
import base64
import io

_LOGGER = logging.getLogger(__name__)

# LOW-003 Fix: Import defaults from const.py instead of hardcoding
from .const import (
    DEFAULT_DETECTOR_CONFIDENCE,
    DEFAULT_FACE_CONFIDENCE,
    DEFAULT_FACE_MATCH_THRESHOLD,
    DEFAULT_ANALYSIS_FRAME_INTERVAL,
    DEFAULT_OVERLAY_SMOOTHING,
    DEFAULT_OVERLAY_SMOOTHING_ALPHA,
)

# Import database for analysis runs tracking
from .database import get_database

# ===== Memory Management Constants (HIGH-005 Fix) =====
# Limit the number of faces with embedded thumbnails to prevent memory exhaustion
# Each base64 thumbnail is ~6KB (80x80 JPEG), limiting to 50 faces = ~300KB max per analysis
MAX_FACES_WITH_THUMBS = 50
# Maximum thumbnail dimension to prevent oversized crops
MAX_THUMB_SIZE = 80
# JPEG quality for thumbnails (lower = smaller file)
THUMB_JPEG_QUALITY = 70
# Face retry confidence multiplier
FACE_RETRY_CONFIDENCE_MULTIPLIER = 0.6
# ===== End Memory Management Constants =====

from datetime import datetime
from typing import Any

# Lazy access to stats tracker from helpers module
def _get_inference_stats() -> Any:
    """Get the inference stats tracker from helpers module."""
    try:
        from .helpers import get_inference_stats
        return get_inference_stats()
    except ImportError:
        return None

try:
    import numpy as np
    from PIL import Image
    from PIL import ImageDraw
except Exception:
    np = None
    Image = None
    ImageDraw = None

try:
    import tflite_runtime.interpreter as tflite
except Exception:
    tflite = None


async def _get_video_fps(video_path: str) -> float:
    """Get the FPS of a video file using ffprobe.
    
    Returns the detected FPS or 15.0 as fallback.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        if stdout:
            fps_str = stdout.decode().strip()
            if "/" in fps_str:
                num, den = fps_str.split("/")
                return float(num) / float(den)
            return float(fps_str)
    except Exception as e:
        _LOGGER.debug("Failed to get video FPS: %s", e)
    return 15.0  # Fallback to 15 FPS


def _safe_mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _write_json(path: str, data: dict) -> None:
    """Synchronous JSON write - use _write_json_async in async contexts."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def _write_json_async(path: str, data: dict) -> None:
    """v1.1.1: Async JSON write to avoid blocking event loop."""
    def _write() -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    await asyncio.get_event_loop().run_in_executor(None, _write)


def _safe_float_list(values: list[Any]) -> list[float]:
    out: list[float] = []
    for v in values:
        try:
            out.append(float(v))
        except (ValueError, TypeError):
            continue
    return out


def _normalize_embedding(embedding: list[float]) -> list[float]:
    if not embedding:
        return []
    if np is not None:
        vec = np.array(embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm == 0:
            return embedding
        return (vec / norm).astype(float).tolist()
    # Fallback ohne numpy
    norm = sum((v * v) for v in embedding) ** 0.5
    if norm == 0:
        return embedding
    return [v / norm for v in embedding]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    if np is not None:
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        if va.size != vb.size:
            return 0.0
        denom = (np.linalg.norm(va) * np.linalg.norm(vb))
        if denom == 0:
            return 0.0
        return float(np.dot(va, vb) / denom)
    # Fallback ohne numpy
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _compute_centroid(embeddings: list) -> list[float] | None:
    """Compute the centroid (average) of multiple embeddings."""
    if not embeddings:
        return None
    
    vectors = []
    for emb in embeddings:
        if isinstance(emb, dict):
            emb = emb.get("vector", [])
        emb_list = _safe_float_list(emb)
        if emb_list:
            vectors.append(emb_list)
    
    if not vectors:
        return None
    
    # All vectors should have the same dimension
    dim = len(vectors[0])
    centroid = [0.0] * dim
    
    for vec in vectors:
        if len(vec) != dim:
            continue
        for i in range(dim):
            centroid[i] += vec[i]
    
    n = len(vectors)
    centroid = [c / n for c in centroid]
    
    # Normalize the centroid
    norm = sum(c * c for c in centroid) ** 0.5
    if norm > 0:
        centroid = [c / norm for c in centroid]
    
    return centroid


def _check_negative_samples(embedding: list[float], person: dict[str, Any], neg_threshold: float = 0.75) -> bool:
    """Check if embedding matches any negative samples for this person.
    
    Returns True if the embedding is similar to a negative sample (should be rejected).
    """
    negative_samples = person.get("negative_embeddings", [])
    if not negative_samples:
        return False
    
    for neg in negative_samples:
        if isinstance(neg, dict):
            neg = neg.get("vector", [])
        neg_list = _safe_float_list(neg)
        if not neg_list:
            continue
        sim = _cosine_similarity(embedding, neg_list)
        if sim >= neg_threshold:
            return True  # This face is similar to a "NOT this person" sample
    
    return False


def _is_no_face(embedding: list[float], no_face_embeddings: list[dict[str, Any]], threshold: float = 0.75) -> bool:
    """Check if embedding matches any 'no face' (false positive) embedding.
    
    Args:
        embedding: Face embedding to check
        no_face_embeddings: List of known false positive embeddings
        threshold: Similarity threshold (default 0.75)
    
    Returns:
        True if this is likely a false positive (not a real face)
    """
    if not embedding or not no_face_embeddings:
        return False
    
    for no_face in no_face_embeddings:
        if isinstance(no_face, dict):
            no_face_vec = no_face.get("vector", [])
        else:
            no_face_vec = no_face
        
        no_face_list = _safe_float_list(no_face_vec)
        if not no_face_list:
            continue
        
        sim = _cosine_similarity(embedding, no_face_list)
        if sim >= threshold:
            return True  # This is a known false positive
    
    return False


def _match_face(embedding: list[float], people: list[dict[str, Any]], threshold: float, no_face_embeddings: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Match a face embedding against people database using centroids.
    
    Uses pre-computed centroids for faster matching. Falls back to
    comparing against all embeddings if no centroid is available.
    
    Also checks negative samples to prevent false matches.
    Checks global no_face_embeddings to filter out false positives.
    """
    if not embedding or not people:
        return None
    
    # First check if this is a known false positive (not a real face)
    if no_face_embeddings and _is_no_face(embedding, no_face_embeddings):
        return {"is_no_face": True}  # Signal that this should be filtered out
    
    candidates = []
    
    for person in people:
        p_id = person.get("id")
        p_name = person.get("name")
        
        # Check negative samples first - if this face matches a "NOT this person" sample, skip
        if _check_negative_samples(embedding, person):
            continue  # Skip this person due to negative sample match
        
        # Try centroid first (faster, more robust)
        centroid = person.get("centroid")
        if centroid:
            centroid_list = _safe_float_list(centroid)
            if centroid_list:
                score = _cosine_similarity(embedding, centroid_list)
                if score >= threshold:
                    candidates.append({
                        "person_id": p_id, 
                        "name": p_name, 
                        "similarity": round(float(score), 4)
                    })
                continue  # Skip individual embeddings if centroid exists
        
        # Fallback: compare against all embeddings (old method)
        best_emb_score = -1.0
        for emb in person.get("embeddings", []) or []:
            if isinstance(emb, dict):
                emb = emb.get("vector", [])
            emb_list = _safe_float_list(emb)
            if not emb_list:
                continue
            score = _cosine_similarity(embedding, emb_list)
            if score > best_emb_score:
                best_emb_score = score
        
        if best_emb_score >= threshold:
            candidates.append({
                "person_id": p_id,
                "name": p_name,
                "similarity": round(float(best_emb_score), 4)
            })
    
    # Return the best candidate (highest similarity)
    if candidates:
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        return candidates[0]
    return None


MODEL_DIR_NAME = "_models"
MODEL_CPU_URL = "https://github.com/google-coral/test_data/raw/master/ssd_mobilenet_v2_coco_quant_postprocess.tflite"
MODEL_CORAL_URL = "https://github.com/google-coral/test_data/raw/master/ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite"
LABELS_URL = "https://github.com/google-coral/test_data/raw/master/coco_labels.txt"


def detect_available_devices() -> list[str]:
    devices = ["cpu"]
    if tflite is None:
        return devices
    try:
        tflite.load_delegate("libedgetpu.so.1")
        devices.append("coral_usb")
    except Exception:
        pass
    return devices


def _download_file(url: str, dest: str) -> None:
    _safe_mkdir(os.path.dirname(dest))
    if not os.path.exists(dest):
        urllib.request.urlretrieve(url, dest)


def _ensure_models(output_root: str, device: str) -> tuple[str, dict[int, str]]:
    model_dir = os.path.join(output_root, MODEL_DIR_NAME)
    _safe_mkdir(model_dir)

    labels_path = os.path.join(model_dir, "coco_labels.txt")
    _download_file(LABELS_URL, labels_path)

    if device == "coral_usb":
        model_path = os.path.join(model_dir, "ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite")
        _download_file(MODEL_CORAL_URL, model_path)
    else:
        model_path = os.path.join(model_dir, "ssd_mobilenet_v2_coco_quant_postprocess.tflite")
        _download_file(MODEL_CPU_URL, model_path)

    labels = {}
    try:
        with open(labels_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f.readlines()):
                label = line.strip()
                if label:
                    labels[i] = label
    except OSError:
        labels = {}

    return model_path, labels


def _build_interpreter(model_path: str, device: str) -> Any:
    if tflite is None:
        raise RuntimeError("tflite-runtime not available")
    if device == "coral_usb":
        delegate = tflite.load_delegate("libedgetpu.so.1")
        return tflite.Interpreter(model_path=model_path, experimental_delegates=[delegate])
    return tflite.Interpreter(model_path=model_path)


def _parse_outputs(output_details: list[dict[str, Any]], outputs: list[Any]) -> tuple[Any, Any, Any, int]:
    boxes = classes = scores = None
    count = 0
    for detail, output in zip(output_details, outputs):
        shape = output.shape
        name = (detail.get("name") or "").lower()
        if "boxes" in name:
            boxes = output
        elif "scores" in name:
            scores = output
        elif "classes" in name:
            classes = output
        elif "count" in name or "num" in name:
            try:
                count = int(output[0])
            except (ValueError, TypeError, IndexError):
                count = int(output.reshape(-1)[0])
        elif len(shape) == 3 and shape[-1] == 4:
            boxes = output
        elif len(shape) == 2 and shape[-1] >= 1:
            if scores is None and output.dtype in (np.float32, np.float16, np.float64):
                scores = output
            elif classes is None:
                classes = output
    if boxes is None or classes is None or scores is None:
        raise RuntimeError("Unable to parse detection outputs")
    if count == 0:
        count = min(boxes.shape[1], scores.shape[1], classes.shape[1])
    return boxes, classes, scores, count


def _run_detection(
    frame_path: str,
    interpreter,
    labels: dict[int, str],
    score_threshold: float,
) -> tuple[list[dict[str, Any]], tuple[int, int]]:
    if np is None or Image is None:
        raise RuntimeError("numpy/Pillow not available")

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    img = Image.open(frame_path).convert("RGB")
    frame_width, frame_height = img.size

    input_shape = input_details[0]["shape"]
    target_h, target_w = int(input_shape[1]), int(input_shape[2])
    img_resized = img.resize((target_w, target_h))
    input_data = np.expand_dims(np.array(img_resized, dtype=np.uint8), axis=0)

    interpreter.set_tensor(input_details[0]["index"], input_data)
    interpreter.invoke()

    outputs = [interpreter.get_tensor(d["index"]) for d in output_details]
    boxes, classes, scores, count = _parse_outputs(output_details, outputs)

    detections = []
    for i in range(int(count)):
        score = float(scores[0][i])
        if score < score_threshold:
            continue
        cls_id = int(classes[0][i])
        label = labels.get(cls_id, str(cls_id))
        ymin, xmin, ymax, xmax = boxes[0][i]
        x = int(xmin * frame_width)
        y = int(ymin * frame_height)
        w = int((xmax - xmin) * frame_width)
        h = int((ymax - ymin) * frame_height)
        detections.append({
            "label": label,
            "score": round(score, 3),
            "box": {"x": x, "y": y, "w": w, "h": h},
        })

    return detections, (frame_width, frame_height)


def _annotate_frame(frame_path: str, detections: list[dict[str, Any]], out_path: str, faces: list[dict[str, Any]] = None) -> None:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow not available")

    img = Image.open(frame_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    img_w, img_h = img.size

    # Draw object detections (red boxes)
    for det in detections:
        box = det.get("box") or {}
        x = int(box.get("x", 0))
        y = int(box.get("y", 0))
        w = int(box.get("w", 0))
        h = int(box.get("h", 0))
        label = det.get("label", "obj")
        score = det.get("score")
        text = f"{label} {score:.2f}" if isinstance(score, (int, float)) else str(label)

        # Clamp coordinates to image bounds to avoid PIL errors
        x = max(0, min(x, img_w - 1))
        y = max(0, min(y, img_h - 1))
        x2 = max(x + 1, min(x + w, img_w))
        y2 = max(y + 1, min(y + h, img_h))
        draw.rectangle([x, y, x2, y2], outline=(255, 64, 64), width=2)

        text_w = max(8 * len(text), 20)
        text_h = 16
        tx1, ty1 = x, max(0, y - text_h)
        tx2, ty2 = min(x + text_w + 6, img_w), y
        if ty2 > ty1:  # Only draw if valid rectangle
            draw.rectangle([tx1, ty1, tx2, ty2], fill=(0, 0, 0))
            draw.text((tx1 + 3, ty1 + 2), text, fill=(255, 255, 255))

    # Draw face detections (orange boxes)
    if faces:
        for face in faces:
            box = face.get("box") or {}
            x = int(box.get("x", 0))
            y = int(box.get("y", 0))
            w = int(box.get("w", 0))
            h = int(box.get("h", 0))
            score = face.get("score", 0)
            match = face.get("match")
            
            # Create label: person name if matched, otherwise "face"
            if match and match.get("name"):
                label = match["name"]
            else:
                label = "face"
            text = f"{label} {score:.2f}" if isinstance(score, (int, float)) else str(label)

            # Clamp coordinates to image bounds to avoid PIL errors
            x = max(0, min(x, img_w - 1))
            y = max(0, min(y, img_h - 1))
            x2 = max(x + 1, min(x + w, img_w))
            y2 = max(y + 1, min(y + h, img_h))
            # Orange color for faces: RGB(255, 165, 0)
            draw.rectangle([x, y, x2, y2], outline=(255, 165, 0), width=3)

            text_w = max(8 * len(text), 20)
            text_h = 16
            tx1, ty1 = x, max(0, y - text_h)
            tx2, ty2 = min(x + text_w + 6, img_w), y
            if ty2 > ty1:  # Only draw if valid rectangle
                draw.rectangle([tx1, ty1, tx2, ty2], fill=(255, 165, 0))
                draw.text((tx1 + 3, ty1 + 2), text, fill=(0, 0, 0))

    img.save(out_path, "JPEG", quality=90)


def _bbox_iou(box_a: dict[str, Any], box_b: dict[str, Any]) -> float:
    """Compute IoU for two boxes with keys x, y, w, h."""
    try:
        ax1 = float(box_a.get("x", 0))
        ay1 = float(box_a.get("y", 0))
        ax2 = ax1 + float(box_a.get("w", 0))
        ay2 = ay1 + float(box_a.get("h", 0))
        bx1 = float(box_b.get("x", 0))
        by1 = float(box_b.get("y", 0))
        bx2 = bx1 + float(box_b.get("w", 0))
        by2 = by1 + float(box_b.get("h", 0))
    except Exception:
        return 0.0

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0

    area_a = max(0.0, (ax2 - ax1)) * max(0.0, (ay2 - ay1))
    area_b = max(0.0, (bx2 - bx1)) * max(0.0, (by2 - by1))
    union = area_a + area_b - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


def _smooth_boxes(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    alpha: float,
    match_label: bool = True,
) -> list[dict[str, Any]]:
    """Smooth boxes using EMA with optional label matching."""
    if not current:
        return []
    if not previous:
        return current

    smoothed: list[dict[str, Any]] = []
    for obj in current:
        cur_box = obj.get("box") or {}
        best_prev = None
        best_iou = 0.0
        for prev in previous:
            if match_label and prev.get("label") != obj.get("label"):
                continue
            iou = _bbox_iou(cur_box, prev.get("box") or {})
            if iou > best_iou:
                best_iou = iou
                best_prev = prev

        if best_prev and best_iou > 0:
            prev_box = best_prev.get("box") or {}
            new_box = {
                "x": int(round(alpha * float(cur_box.get("x", 0)) + (1 - alpha) * float(prev_box.get("x", 0)))),
                "y": int(round(alpha * float(cur_box.get("y", 0)) + (1 - alpha) * float(prev_box.get("y", 0)))),
                "w": int(round(alpha * float(cur_box.get("w", 0)) + (1 - alpha) * float(prev_box.get("w", 0)))),
                "h": int(round(alpha * float(cur_box.get("h", 0)) + (1 - alpha) * float(prev_box.get("h", 0)))),
            }
            new_obj = dict(obj)
            new_obj["box"] = new_box
            smoothed.append(new_obj)
        else:
            smoothed.append(obj)
    return smoothed


def _smooth_detections_for_overlay(detections: list[dict[str, Any]], alpha: float) -> list[dict[str, Any]]:
    """Apply EMA smoothing to object/face boxes for overlay rendering."""
    if not detections:
        return detections

    smoothed: list[dict[str, Any]] = []
    prev_objects: list[dict[str, Any]] = []
    prev_faces: list[dict[str, Any]] = []

    for det in detections:
        objects = det.get("objects", []) or []
        faces = det.get("faces", []) or []

        smoothed_objects = _smooth_boxes(objects, prev_objects, alpha, match_label=True)
        smoothed_faces = _smooth_boxes(faces, prev_faces, alpha, match_label=False)

        det_copy = dict(det)
        det_copy["objects"] = smoothed_objects
        if "faces" in det_copy:
            det_copy["faces"] = smoothed_faces

        smoothed.append(det_copy)
        prev_objects = smoothed_objects
        prev_faces = smoothed_faces

    return smoothed


async def _render_annotated_video(
    frames: list[str],
    detections: list[dict[str, Any]],
    output_dir: str,
    interval_s: int,
    video_path: str | None = None,
) -> str:
    """Render annotated video from frames with bounding boxes.
    
    v1.1.2: Uses original video FPS for smooth playback.
    Frames are duplicated to match the original FPS, creating
    smooth transitions instead of 0.5 FPS stuttering.
    """
    if not frames:
        raise RuntimeError("No frames to annotate")
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow not available")

    annotated_dir = os.path.join(output_dir, "annotated")
    _safe_mkdir(annotated_dir)

    for idx, frame_path in enumerate(frames):
        dets = detections[idx].get("objects", []) if idx < len(detections) else []
        faces = detections[idx].get("faces", []) if idx < len(detections) else []
        out_path = os.path.join(annotated_dir, f"frame_{idx:04d}.jpg")
        await asyncio.to_thread(_annotate_frame, frame_path, dets, out_path, faces)

    output_video = os.path.join(output_dir, "annotated.mp4")
    
    # v1.1.2: Get original video FPS for smooth playback
    original_fps = 15.0  # Default fallback
    if video_path:
        original_fps = await _get_video_fps(video_path)
    
    # Calculate input framerate (how often we extracted frames)
    input_fps = 1 / max(1, int(interval_s))
    
    # Use ffmpeg to create video with original FPS
    # -framerate: input frame rate (our extracted frames)
    # -r: output frame rate (original video FPS for smooth playback)
    # This duplicates frames to match the original FPS
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-framerate", str(input_fps),
        "-i", os.path.join(annotated_dir, "frame_%04d.jpg"),
        "-c:v", "libx264",
        "-r", str(original_fps),
        "-pix_fmt", "yuv420p",
        output_video,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    
    try:
        await process.wait()
    except Exception:
        # MED-002 Fix: Terminate FFmpeg process on error
        if process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except Exception:
                process.kill()
        raise

    if not os.path.exists(output_video):
        raise RuntimeError("Annotated video not created")
    
    # v1.1.2: Clean up annotated frames after video creation to save disk space
    # The video is the final output, individual frames are no longer needed
    # Run blocking I/O in executor to avoid blocking event loop
    try:
        if os.path.isdir(annotated_dir):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, shutil.rmtree, annotated_dir)
    except OSError:
        pass  # Best effort cleanup, don't fail if frames can't be deleted
    
    return output_video


async def extract_frames(video_path: str, output_dir: str, interval_s: int = 2) -> list[str]:
    """Extract frames from a video using ffmpeg. Returns list of frame files.
    
    MED-002 Fix: Uses try/finally to ensure FFmpeg process is terminated on error.
    """
    _safe_mkdir(output_dir)
    pattern = os.path.join(output_dir, "frame_%04d.jpg")
    fps = 1 / max(1, int(interval_s))

    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-vf",
        f"fps={fps}",
        pattern,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    
    try:
        await process.wait()
    except Exception:
        # MED-002 Fix: Terminate FFmpeg process on error
        if process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except Exception:
                process.kill()
        raise

    # v1.1.1 fix: Run blocking I/O in executor to avoid blocking event loop
    def _list_frames() -> list[str]:
        return sorted(
            [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.startswith("frame_")]
        )
    
    loop = asyncio.get_event_loop()
    files = await loop.run_in_executor(None, _list_frames)
    return files


def _extract_camera_from_path(video_path: str) -> str:
    """Extract camera name from video path.
    
    Supports paths like:
    - /recordings/camera_name/video.mp4
    - /ring_recordings/camera_name/video.mp4
    - /media/rtsp_recorder/recordings/camera_name/video.mp4
    
    Args:
        video_path: Full path to video file
        
    Returns:
        Camera name or "unknown" if not found
    """
    path_parts = video_path.replace("\\", "/").split("/")
    for i, part in enumerate(path_parts):
        if part in ("recordings", "ring_recordings") and i + 1 < len(path_parts):
            next_part = path_parts[i + 1]
            if next_part != "_analysis":
                return next_part
    return "unknown"


def _initialize_analysis_result(
    video_path: str,
    objects: list[str] | None,
    device: str | None,
    timestamp: str,
    interval_s: int,
    video_size_mb: float | None,
    perf_snapshot: dict | None,
    overlay_smoothing: bool,
    overlay_smoothing_alpha: float,
    face_enabled: bool,
    face_confidence: float,
    face_match_threshold: float,
    face_store_embeddings: bool,
) -> dict[str, Any]:
    """Initialize the analysis result dictionary.
    
    Args:
        video_path: Path to the video file
        objects: List of objects to detect
        device: Detection device (cpu/coral_usb)
        timestamp: Analysis timestamp
        interval_s: Frame extraction interval
        video_size_mb: Video file size in MB
        perf_snapshot: Performance snapshot data
        overlay_smoothing: Enable overlay smoothing
        overlay_smoothing_alpha: Smoothing alpha value
        face_enabled: Enable face detection
        face_confidence: Face detection confidence
        face_match_threshold: Face matching threshold
        face_store_embeddings: Store face embeddings
        
    Returns:
        Initialized result dictionary
    """
    return {
        "status": "started",
        "video_path": video_path,
        "objects": objects or [],
        "device": device or "cpu",
        "created_utc": timestamp,
        "frame_interval": interval_s,
        "video_size_mb": video_size_mb,
        "perf_snapshot": perf_snapshot or {},
        "frames": [],
        "detections": [],
        "overlay_smoothing": bool(overlay_smoothing),
        "overlay_smoothing_alpha": float(overlay_smoothing_alpha),
        "face_enabled": bool(face_enabled),
        "face_confidence": float(face_confidence),
        "face_match_threshold": float(face_match_threshold),
        "face_store_embeddings": bool(face_store_embeddings),
        "faces_detected": 0,
        "faces_matched": 0,
        "frame_width": None,
        "frame_height": None,
        "frame_count": 0,
        "duration_sec": 0,
    }


async def _create_db_analysis_run(
    video_path: str,
    camera_name: str,
    interval_s: int,
    video_size_mb: float | None,
    device: str,
    job_dir: str,
) -> int | None:
    """Create an analysis run entry in the database.
    
    Args:
        video_path: Path to video file
        camera_name: Extracted camera name
        interval_s: Frame extraction interval
        video_size_mb: Video size in MB
        device: Detection device
        job_dir: Analysis job directory
        
    Returns:
        Analysis run ID or None if creation failed
    """
    try:
        db = get_database()
        if db:
            analysis_run_id = db.create_analysis_run(
                video_path=video_path,
                camera_name=camera_name,
                frame_interval=interval_s,
                video_size_mb=video_size_mb,
                device_used=device
            )
            if analysis_run_id:
                db.update_analysis_run(run_id=analysis_run_id, analysis_path=job_dir)
            return analysis_run_id
    except Exception as db_err:
        _LOGGER.warning("Could not create analysis_run entry: %s", db_err)
    return None


def _create_face_thumbnail(
    face_box: dict[str, int],
    frame_img: Any,
) -> str | None:
    """Create a base64-encoded thumbnail from a detected face.
    
    Args:
        face_box: Face bounding box with x, y, w, h
        frame_img: PIL Image of the frame
        
    Returns:
        Base64-encoded data URL or None if creation failed
    """
    if frame_img is None:
        return None
    try:
        x = max(int(face_box.get("x", 0)), 0)
        y = max(int(face_box.get("y", 0)), 0)
        w = max(int(face_box.get("w", 0)), 1)
        h = max(int(face_box.get("h", 0)), 1)
        x2 = min(x + w, frame_img.width)
        y2 = min(y + h, frame_img.height)
        crop = frame_img.crop((x, y, x2, y2))
        crop = crop.resize((MAX_THUMB_SIZE, MAX_THUMB_SIZE))
        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=THUMB_JPEG_QUALITY)
        thumb_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{thumb_b64}"
    except (OSError, ValueError):
        return None


def _normalize_and_match_face(
    face: dict[str, Any],
    people_db: list[dict[str, Any]] | None,
    face_match_threshold: float,
    no_face_embeddings: list[dict[str, Any]] | None,
    face_store_embeddings: bool,
    frame_img: Any,
    detections: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, bool]:
    """Normalize a detected face and attempt to match against people DB.
    
    Args:
        face: Raw face detection dict with box, score, embedding
        people_db: List of known people with embeddings
        face_match_threshold: Minimum similarity for a match
        no_face_embeddings: Embeddings of known false positives
        face_store_embeddings: Whether to store embeddings in output
        frame_img: PIL Image of the frame for thumbnail
        detections: Current detections list (for thumbnail count)
        
    Returns:
        Tuple of (normalized face_item or None, was_matched)
    """
    face_box = face.get("box") or {}
    score = face.get("score", 0.0)
    emb = face.get("embedding")
    emb_source = (face.get("embedding_source") or "").lower()
    
    emb_list = _safe_float_list(emb) if isinstance(emb, list) else []
    if emb_list:
        emb_list = _normalize_embedding(emb_list)
    
    match = None
    was_matched = False
    
    if emb_list and people_db:
        match = _match_face(emb_list, people_db, face_match_threshold, no_face_embeddings)
        # Check if this is a known false positive (not a real face)
        if match and match.get("is_no_face"):
            return None, False  # Skip this face entirely
        if match:
            was_matched = True
    
    # Count existing thumbnails
    total_thumbs_created = sum(
        1 for det in detections 
        for f in det.get("faces", []) 
        if f.get("thumb")
    )
    
    # Create thumbnail if under limit
    thumb_data = None
    if total_thumbs_created < MAX_FACES_WITH_THUMBS:
        thumb_data = _create_face_thumbnail(face_box, frame_img)
    
    face_item: dict[str, Any] = {
        "score": round(float(score), 3),
        "box": {
            "x": int(face_box.get("x", 0)),
            "y": int(face_box.get("y", 0)),
            "w": int(face_box.get("w", 0)),
            "h": int(face_box.get("h", 0)),
        },
    }
    
    if match:
        face_item["match"] = match
    if emb_list and face_store_embeddings:
        face_item["embedding"] = emb_list
    if emb_source:
        face_item["embedding_source"] = emb_source
    if thumb_data:
        face_item["thumb"] = thumb_data
    
    return face_item, was_matched


async def _finalize_analysis_run(
    analysis_run_id: int | None,
    result: dict[str, Any],
) -> None:
    """Update the analysis run entry with final statistics.
    
    Args:
        analysis_run_id: Database ID of the analysis run
        result: Final result dictionary
    """
    if not analysis_run_id:
        return
    try:
        db = get_database()
        if db:
            # Extract unique objects and count persons from detections
            unique_objects: set[str] = set()
            persons_count = 0
            for det in result.get("detections", []):
                for obj in det.get("objects", []):
                    label = obj.get("label", "")
                    if label:
                        unique_objects.add(label)
                        if label == "person":
                            persons_count += 1
            
            db.update_analysis_run(
                run_id=analysis_run_id,
                status="completed",
                frame_count=result.get("frame_count", 0),
                faces_detected=result.get("faces_detected", 0),
                faces_matched=result.get("faces_matched", 0),
                processing_time_sec=result.get("processing_time_seconds"),
                objects_found=",".join(sorted(unique_objects)) if unique_objects else None,
                persons_detected=persons_count,
            )
    except Exception as db_err:
        _LOGGER.warning("Could not update analysis_run: %s", db_err)


def _is_point_in_box(
    point_x: int,
    point_y: int,
    box: dict[str, Any],
) -> bool:
    """Check if a point is inside a bounding box.
    
    Args:
        point_x: X coordinate of the point
        point_y: Y coordinate of the point
        box: Bounding box with x, y, w, h
        
    Returns:
        True if point is inside box
    """
    px = int(box.get("x", 0))
    py = int(box.get("y", 0))
    pw = int(box.get("w", 0))
    ph = int(box.get("h", 0))
    return px <= point_x <= px + pw and py <= point_y <= py + ph


async def _try_movenet_head_detection(
    session: Any,
    face_url: str,
    frame_bytes: bytes,
    frame_path: str,
    frame_img: Any,
    person_boxes: list[dict[str, Any]],
    device: str,
    embed_flag: str,
) -> dict[str, Any] | None:
    """Try to detect a head using MoveNet pose estimation.
    
    Only returns a result if:
    - At least 3 keypoints were found (nose + eyes or ears)
    - The detected head is within a person bounding box
    
    Args:
        session: aiohttp session
        face_url: Face detection API URL
        frame_bytes: JPEG bytes of the frame
        frame_path: Path to frame file
        frame_img: PIL Image of the frame
        person_boxes: List of detected person bounding boxes
        device: Detection device (coral_usb, cpu)
        embed_flag: "1" to generate embeddings
        
    Returns:
        Face dict with box, score, method, embedding or None
    """
    if not person_boxes:
        return None
    
    try:
        movenet_form = aiohttp.FormData()
        movenet_form.add_field(
            "file", frame_bytes,
            filename=os.path.basename(frame_path),
            content_type="image/jpeg"
        )
        movenet_form.add_field("min_confidence", "0.3")
        
        async with session.post(
            f"{face_url.rstrip('/')}/head_movenet",
            data=movenet_form,
            timeout=30
        ) as movenet_resp:
            if movenet_resp.status != 200:
                return None
            
            movenet_data = await movenet_resp.json()
            head_box_data = movenet_data.get("head_box")
            
            if not head_box_data or not head_box_data.get("box"):
                return None
            
            keypoints_used = head_box_data.get("keypoints_used", 0)
            if keypoints_used < 3:
                return None
            
            hbox = head_box_data["box"]
            hx = int(hbox.get("x", 0))
            hy = int(hbox.get("y", 0))
            hw = int(hbox.get("w", 0))
            hh = int(hbox.get("h", 0))
            head_center_x = hx + hw // 2
            head_center_y = hy + hh // 2
            
            # Verify head is within a detected person box
            head_in_person = any(
                _is_point_in_box(head_center_x, head_center_y, pobj.get("box") or {})
                for pobj in person_boxes
            )
            
            if not head_in_person:
                return None
            
            head_face: dict[str, Any] = {
                "score": head_box_data.get("confidence", 0.5),
                "box": hbox,
                "method": "movenet",
                "keypoints_used": keypoints_used,
            }
            
            # Generate embedding if requested
            if frame_img is not None and embed_flag == "1":
                try:
                    hx2 = min(hx + hw, frame_img.width)
                    hy2 = min(hy + hh, frame_img.height)
                    head_crop = frame_img.crop((hx, hy, hx2, hy2))
                    head_buf = io.BytesIO()
                    head_crop.save(head_buf, format="JPEG", quality=85)
                    head_bytes = head_buf.getvalue()
                    
                    embed_form = aiohttp.FormData()
                    embed_form.add_field(
                        "file", head_bytes,
                        filename="head.jpg",
                        content_type="image/jpeg"
                    )
                    embed_form.add_field("device", device)
                    
                    async with session.post(
                        f"{face_url.rstrip('/')}/embed_face",
                        data=embed_form,
                        timeout=30
                    ) as embed_resp:
                        if embed_resp.status == 200:
                            embed_data = await embed_resp.json()
                            if embed_data.get("embedding"):
                                head_face["embedding"] = embed_data["embedding"]
                                head_face["embedding_source"] = "movenet"
                except Exception as embed_err:
                    _LOGGER.debug("MoveNet head embedding failed: %s", embed_err)
            
            _LOGGER.debug(
                "MoveNet detected head with %d keypoints (validated in person box)",
                keypoints_used
            )
            return head_face
            
    except Exception as movenet_err:
        _LOGGER.debug("MoveNet fallback failed: %s", movenet_err)
        return None


async def _detect_faces_with_retry(
    session: Any,
    face_url: str,
    frame_bytes: bytes,
    frame_path: str,
    device: str,
    face_confidence: float,
    embed_flag: str,
) -> tuple[dict[str, Any], float]:
    """Detect faces in a frame with automatic retry at lower confidence.
    
    Args:
        session: aiohttp session
        face_url: Face detection API URL
        frame_bytes: JPEG bytes of the frame
        frame_path: Path to frame file
        device: Detection device
        face_confidence: Minimum confidence threshold
        embed_flag: "1" to generate embeddings
        
    Returns:
        Tuple of (response data dict, detection time in ms)
    """
    form = aiohttp.FormData()
    form.add_field(
        "file", frame_bytes,
        filename=os.path.basename(frame_path),
        content_type="image/jpeg"
    )
    form.add_field("device", device)
    form.add_field("confidence", str(face_confidence))
    form.add_field("embed", embed_flag)
    
    _detect_start = time.perf_counter()
    async with session.post(
        f"{face_url.rstrip('/')}/faces",
        data=form,
        timeout=60
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Face detector error {resp.status}")
        data = await resp.json()
    
    # Retry once with lower confidence if no faces found
    if not (data.get("faces") or []) and float(face_confidence) > 0.25:
        retry_conf = max(DEFAULT_FACE_CONFIDENCE, float(face_confidence) * FACE_RETRY_CONFIDENCE_MULTIPLIER)
        form_retry = aiohttp.FormData()
        form_retry.add_field(
            "file", frame_bytes,
            filename=os.path.basename(frame_path),
            content_type="image/jpeg"
        )
        form_retry.add_field("device", device)
        form_retry.add_field("confidence", str(retry_conf))
        form_retry.add_field("embed", embed_flag)
        
        async with session.post(
            f"{face_url.rstrip('/')}/faces",
            data=form_retry,
            timeout=60
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
    
    _detect_ms = (time.perf_counter() - _detect_start) * 1000
    return data, _detect_ms


async def _detect_faces_in_crop(
    session: Any,
    face_url: str,
    crop_img: Any,
    device: str,
    confidence: float,
    embed_flag: str,
    scale_factor: float,
    offset_x: int,
    offset_y: int,
) -> list[dict[str, Any]]:
    """Detect faces in a cropped image region and adjust coordinates.
    
    Args:
        session: aiohttp session
        face_url: Face detection API URL
        crop_img: PIL Image of the crop
        device: Detection device
        confidence: Minimum confidence threshold
        embed_flag: "1" to generate embeddings
        scale_factor: Scale factor used for upscaling
        offset_x: X offset to add to face boxes
        offset_y: Y offset to add to face boxes
        
    Returns:
        List of face dicts with adjusted coordinates
    """
    buf = io.BytesIO()
    crop_img.save(buf, format="JPEG", quality=80)
    crop_bytes = buf.getvalue()
    
    crop_form = aiohttp.FormData()
    crop_form.add_field("file", crop_bytes, filename="crop.jpg", content_type="image/jpeg")
    crop_form.add_field("device", device)
    crop_form.add_field("confidence", str(confidence))
    crop_form.add_field("embed", embed_flag)
    
    async with session.post(f"{face_url.rstrip('/')}/faces", data=crop_form, timeout=60) as resp:
        if resp.status != 200:
            return []
        crop_data = await resp.json()
    
    faces_out: list[dict[str, Any]] = []
    for cf in (crop_data.get("faces") or []):
        cbox = cf.get("box") or {}
        sx = float(cbox.get("x", 0)) / scale_factor
        sy = float(cbox.get("y", 0)) / scale_factor
        sw = float(cbox.get("w", 0)) / scale_factor
        sh = float(cbox.get("h", 0)) / scale_factor
        cf["box"] = {
            "x": int(sx) + offset_x,
            "y": int(sy) + offset_y,
            "w": int(sw),
            "h": int(sh),
        }
        faces_out.append(cf)
    
    return faces_out


async def _try_detect_faces_in_person_crops(
    session: Any,
    face_url: str,
    frame_img: Any,
    person_boxes: list[dict[str, Any]],
    device: str,
    face_confidence: float,
    embed_flag: str,
) -> list[dict[str, Any]]:
    """Try to detect faces in person bounding box crops with upscaling.
    
    Args:
        session: aiohttp session
        face_url: Face detection API URL
        frame_img: PIL Image of the full frame
        person_boxes: List of person detections with boxes
        device: Detection device
        face_confidence: Base confidence threshold
        embed_flag: "1" to generate embeddings
        
    Returns:
        List of detected faces with adjusted coordinates
    """
    if frame_img is None or not person_boxes:
        return []
    
    extra_faces: list[dict[str, Any]] = []
    
    for pobj in person_boxes:
        box = pobj.get("box") or {}
        x = max(int(box.get("x", 0)), 0)
        y = max(int(box.get("y", 0)), 0)
        w = max(int(box.get("w", 0)), 1)
        h = max(int(box.get("h", 0)), 1)
        
        # Add 10% padding
        pad = int(0.1 * max(w, h))
        x1 = max(x - pad, 0)
        y1 = max(y - pad, 0)
        x2 = min(x + w + pad, frame_img.width)
        y2 = min(y + h + pad, frame_img.height)
        
        # Skip too small crops
        if (x2 - x1) < 40 or (y2 - y1) < 40:
            continue
        
        crop = frame_img.crop((x1, y1, x2, y2))
        
        # Try at original scale
        faces_crop = await _detect_faces_in_crop(
            session, face_url, crop, device,
            float(face_confidence), embed_flag, 1.0, x1, y1
        )
        
        # Try 1.5x upscale for small crops
        if not faces_crop:
            max_dim = max(crop.width, crop.height)
            if max_dim < 160:
                scale = 1.5
                crop_up = crop.resize((int(crop.width * scale), int(crop.height * scale)))
                crop_conf = max(0.15, float(face_confidence) * 0.7)
                faces_crop = await _detect_faces_in_crop(
                    session, face_url, crop_up, device,
                    crop_conf, embed_flag, scale, x1, y1
                )
        
        # Try 2x upscale for very small crops
        if not faces_crop:
            max_dim = max(crop.width, crop.height)
            if max_dim < 120:
                scale = 2.0
                crop_up = crop.resize((int(crop.width * scale), int(crop.height * scale)))
                crop_conf = max(0.1, float(face_confidence) * 0.6)
                faces_crop = await _detect_faces_in_crop(
                    session, face_url, crop_up, device,
                    crop_conf, embed_flag, scale, x1, y1
                )
        
        if faces_crop:
            extra_faces.extend(faces_crop)
    
    return extra_faces


async def analyze_recording(
    video_path: str,
    output_root: str,
    objects: list[str],
    device: str,
    interval_s: int = DEFAULT_ANALYSIS_FRAME_INTERVAL,
    perf_snapshot: dict | None = None,
    detector_url: str | None = None,
    detector_confidence: float = DEFAULT_DETECTOR_CONFIDENCE,
    face_enabled: bool = False,
    face_confidence: float = DEFAULT_FACE_CONFIDENCE,
    face_match_threshold: float = DEFAULT_FACE_MATCH_THRESHOLD,
    face_store_embeddings: bool = False,
    people_db: list[dict[str, Any]] | None = None,
    face_detector_url: str | None = None,
    no_face_embeddings: list[dict[str, Any]] | None = None,
    overlay_smoothing: bool = DEFAULT_OVERLAY_SMOOTHING,
    overlay_smoothing_alpha: float = DEFAULT_OVERLAY_SMOOTHING_ALPHA,
) -> dict:
    """Offline analysis stub: extracts frames and writes a results JSON.

    This function runs locally and prepares data for later detection.
    
    LOW-003 Fix: Default values now sourced from const.py.
    v1.2.0 Refactor: Extracted helper functions to reduce cyclomatic complexity.
    """
    _safe_mkdir(output_root)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    job_dir = os.path.join(output_root, f"analysis_{timestamp}")
    frames_dir = os.path.join(job_dir, "frames")
    _safe_mkdir(frames_dir)

    video_size_mb = None
    if os.path.exists(video_path):
        try:
            video_size_mb = round(os.path.getsize(video_path) / (1024 * 1024), 2)
        except Exception:
            video_size_mb = None

    # v1.2.0 Refactor: Use helper function for result initialization
    result = _initialize_analysis_result(
        video_path=video_path,
        objects=objects,
        device=device,
        timestamp=timestamp,
        interval_s=interval_s,
        video_size_mb=video_size_mb,
        perf_snapshot=perf_snapshot,
        overlay_smoothing=overlay_smoothing,
        overlay_smoothing_alpha=overlay_smoothing_alpha,
        face_enabled=face_enabled,
        face_confidence=face_confidence,
        face_match_threshold=face_match_threshold,
        face_store_embeddings=face_store_embeddings,
    )

    result_path = os.path.join(job_dir, "result.json")
    await _write_json_async(result_path, result)

    # v1.2.0 Refactor: Use helper functions for camera extraction and DB tracking
    extracted_camera = _extract_camera_from_path(video_path)
    analysis_run_id = await _create_db_analysis_run(
        video_path=video_path,
        camera_name=extracted_camera,
        interval_s=interval_s,
        video_size_mb=video_size_mb,
        device=device or "cpu",
        job_dir=job_dir,
    )

    try:
        start_time = time.monotonic()
        frames = await extract_frames(video_path, frames_dir, interval_s)
        duration_sec = round(time.monotonic() - start_time, 2)
        result["frames"] = frames
        result["frame_count"] = len(frames)
        result["duration_sec"] = duration_sec
        result["status"] = "frames_extracted"
        await _write_json_async(result_path, result)

        detections: list[dict[str, Any]] = []

        # Run object detection on extracted frames (optional)
        if frames and objects:
            try:
                frame_w = frame_h = None
                if detector_url:
                    async with aiohttp.ClientSession() as session:
                        for idx, frame_path in enumerate(frames):
                            # v1.1.0 fix: Read file in executor to avoid blocking event loop
                            frame_bytes = await asyncio.to_thread(lambda p=frame_path: open(p, "rb").read())
                            form = aiohttp.FormData()
                            form.add_field("file", frame_bytes, filename=os.path.basename(frame_path), content_type="image/jpeg")
                            form.add_field("objects", json.dumps(objects))
                            form.add_field("device", device)
                            form.add_field("confidence", str(detector_confidence))
                            _detect_start = time.perf_counter()
                            async with session.post(f"{detector_url.rstrip('/')}/detect", data=form, timeout=30) as resp:
                                if resp.status != 200:
                                    raise RuntimeError(f"Detector error {resp.status}")
                                data = await resp.json()
                            _detect_ms = (time.perf_counter() - _detect_start) * 1000
                            _used_device = data.get("device", device)
                            _stats = _get_inference_stats()
                            if _stats:
                                _stats.record(_used_device, _detect_ms, 1)
                            dets = data.get("objects", [])
                            if objects:
                                dets = [d for d in dets if d.get("label") in objects]
                            time_s = idx * interval_s
                            detections.append({"time_s": time_s, "objects": dets})
                            frame_w = data.get("frame_width")
                            frame_h = data.get("frame_height")
                else:
                    if tflite is None or np is None or Image is None:
                        raise RuntimeError("Missing dependencies: tflite-runtime, numpy, Pillow")

                    model_path, labels = await asyncio.to_thread(_ensure_models, output_root, device)
                    interpreter = await asyncio.to_thread(
                        _build_interpreter,
                        model_path,
                        device if device in ("coral_usb",) else "cpu",
                    )
                    await asyncio.to_thread(interpreter.allocate_tensors)

                    for idx, frame_path in enumerate(frames):
                        _detect_start = time.perf_counter()
                        dets, (fw, fh) = await asyncio.to_thread(
                            _run_detection,
                            frame_path,
                            interpreter,
                            labels,
                            score_threshold=detector_confidence,
                        )
                        _detect_ms = (time.perf_counter() - _detect_start) * 1000
                        _stats = _get_inference_stats()
                        if _stats:
                            _stats.record(device, _detect_ms, 1)
                        if objects:
                            dets = [d for d in dets if d["label"] in objects]
                        time_s = idx * interval_s
                        detections.append({"time_s": time_s, "objects": dets})
                        frame_w, frame_h = fw, fh

                result["detections"] = detections
                result["frame_width"] = frame_w
                result["frame_height"] = frame_h

                try:
                    overlay_detections = detections
                    if overlay_smoothing and detections:
                        alpha = max(0.05, min(float(overlay_smoothing_alpha or DEFAULT_OVERLAY_SMOOTHING_ALPHA), 0.95))
                        overlay_detections = _smooth_detections_for_overlay(detections, alpha)
                        result["overlay_smoothing_alpha"] = alpha
                    annotated_video = await _render_annotated_video(frames, overlay_detections, job_dir, interval_s, video_path)
                    result["annotated_video"] = annotated_video
                except Exception as e:
                    result["annotated_video_error"] = str(e)
            except Exception as e:
                result["detection_error"] = str(e)

        # Run face detection + embeddings (optional)
        if frames and face_enabled:
            try:
                face_url = face_detector_url or detector_url
                if not face_url:
                    raise RuntimeError("face detector url missing")

                faces_detected = 0
                faces_matched = 0
                consecutive_face_errors = 0
                max_consecutive_errors = 3  # Stop if 3 frames in a row fail

                async with aiohttp.ClientSession() as session:
                    for idx, frame_path in enumerate(frames):
                        # Only run face detection when a person is detected in this frame
                        person_boxes = []
                        if idx < len(detections):
                            person_boxes = [o for o in (detections[idx].get("objects") or []) if o.get("label") == "person"]
                        if not person_boxes:
                            continue

                        # Skip remaining frames if too many consecutive errors
                        if consecutive_face_errors >= max_consecutive_errors:
                            _LOGGER.warning("Face detection: Skipping remaining frames after %d consecutive errors", max_consecutive_errors)
                            break

                        try:
                            # v1.1.0 fix: Read file in executor to avoid blocking event loop
                            frame_bytes = await asyncio.to_thread(lambda p=frame_path: open(p, "rb").read())
                        except OSError as read_err:
                            _LOGGER.debug("Failed to read frame %d: %s", idx, read_err)
                            consecutive_face_errors += 1
                            continue

                        frame_img = None
                        if Image is not None:
                            try:
                                frame_img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
                            except (OSError, ValueError):
                                frame_img = None

                        embed_flag = "1" if (face_store_embeddings or (people_db and len(people_db) > 0)) else "0"

                        # v1.2.0 Refactor: Use helper function for face detection with retry
                        try:
                            data, _detect_ms = await _detect_faces_with_retry(
                                session=session,
                                face_url=face_url,
                                frame_bytes=frame_bytes,
                                frame_path=frame_path,
                                device=device,
                                face_confidence=float(face_confidence),
                                embed_flag=embed_flag,
                            )
                            _used_device = data.get("device", device)
                            _stats = _get_inference_stats()
                            if _stats:
                                _stats.record(_used_device, _detect_ms, 1)
                            consecutive_face_errors = 0
                        except Exception as face_req_err:
                            _LOGGER.debug("Face detection request failed for frame %d: %s", idx, face_req_err)
                            consecutive_face_errors += 1
                            time_s = idx * interval_s
                            if idx < len(detections):
                                detections[idx]["faces"] = []
                            else:
                                detections.append({"time_s": time_s, "faces": []})
                            continue

                        faces = data.get("faces", []) or []
                        frame_w = data.get("frame_width")
                        frame_h = data.get("frame_height")

                        # v1.2.0 Refactor: Use helper for person crop face detection
                        if not faces and frame_img is not None and idx < len(detections):
                            person_boxes = [o for o in (detections[idx].get("objects") or []) if o.get("label") == "person"]
                            extra_faces = await _try_detect_faces_in_person_crops(
                                session=session,
                                face_url=face_url,
                                frame_img=frame_img,
                                person_boxes=person_boxes,
                                device=device,
                                face_confidence=float(face_confidence),
                                embed_flag=embed_flag,
                            )
                            if extra_faces:
                                faces = extra_faces

                        # v1.2.0 Refactor: Use helper for MoveNet head detection
                        if not faces:
                            movenet_face = await _try_movenet_head_detection(
                                session=session,
                                face_url=face_url,
                                frame_bytes=frame_bytes,
                                frame_path=frame_path,
                                frame_img=frame_img,
                                person_boxes=person_boxes,
                                device=device,
                                embed_flag=embed_flag,
                            )
                            if movenet_face:
                                faces.append(movenet_face)

                        if frame_w and frame_h:
                            result["frame_width"] = frame_w
                            result["frame_height"] = frame_h
                        
                        # v1.2.0 Refactor: Use helper function for face normalization
                        normed_faces = []
                        for face in faces:
                            face_item, was_matched = _normalize_and_match_face(
                                face=face,
                                people_db=people_db,
                                face_match_threshold=face_match_threshold,
                                no_face_embeddings=no_face_embeddings,
                                face_store_embeddings=face_store_embeddings,
                                frame_img=frame_img,
                                detections=detections,
                            )
                            if face_item is None:
                                continue  # Skip false positives
                            if was_matched:
                                faces_matched += 1
                            normed_faces.append(face_item)

                        faces_detected += len(normed_faces)
                        time_s = idx * interval_s
                        if idx < len(detections):
                            detections[idx]["faces"] = normed_faces
                        else:
                            detections.append({"time_s": time_s, "faces": normed_faces})

                result["detections"] = detections
                result["faces_detected"] = faces_detected
                result["faces_matched"] = faces_matched
            except Exception as e:
                result["face_detection_error"] = str(e)

        # Mark analysis as completed successfully
        result["status"] = "completed"
        result["completed_utc"] = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        result["processing_time_seconds"] = round(time.monotonic() - start_time, 2)
        
        # v1.1.2: Update analysis run in SQLite with final stats
        await _finalize_analysis_run(analysis_run_id, result)
        
        # v1.1.0n: Cleanup frames after successful analysis to save disk space
        # Frames are only needed during detection, not afterwards
        # v1.1.1 fix: Run blocking I/O in executor to avoid blocking event loop
        try:
            if os.path.isdir(frames_dir):
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, shutil.rmtree, frames_dir)
                result["frames_cleaned"] = True
        except OSError as cleanup_err:
            result["frames_cleanup_error"] = str(cleanup_err)
        
        await _write_json_async(result_path, result)
        return result
    except asyncio.CancelledError:
        result["status"] = "cancelled"
        result["error"] = "analysis_cancelled"
        # v1.1.2: Update analysis run on cancellation
        if analysis_run_id:
            try:
                db = get_database()
                if db:
                    db.update_analysis_run(
                        run_id=analysis_run_id,
                        status="cancelled",
                        error_message="analysis_cancelled"
                    )
            except Exception:
                pass
        await _write_json_async(result_path, result)
        raise
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        # v1.1.2: Update analysis run on error
        if analysis_run_id:
            try:
                db = get_database()
                if db:
                    db.update_analysis_run(
                        run_id=analysis_run_id,
                        status="error",
                        error_message=str(e)
                    )
            except Exception:
                pass
        await _write_json_async(result_path, result)
        return result
