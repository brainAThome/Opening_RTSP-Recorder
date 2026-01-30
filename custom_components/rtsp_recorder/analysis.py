import asyncio
import json
import logging
import os
import time
import urllib.request
import aiohttp
import base64
import io

_LOGGER = logging.getLogger(__name__)

# ===== Memory Management Constants (HIGH-005 Fix) =====
# Limit the number of faces with embedded thumbnails to prevent memory exhaustion
# Each base64 thumbnail is ~6KB (80x80 JPEG), limiting to 50 faces = ~300KB max per analysis
MAX_FACES_WITH_THUMBS = 50
# Maximum thumbnail dimension to prevent oversized crops
MAX_THUMB_SIZE = 80
# JPEG quality for thumbnails (lower = smaller file)
THUMB_JPEG_QUALITY = 70
# ===== End Memory Management Constants =====

# Lazy access to stats tracker from parent module
def _get_inference_stats():
    """Get the inference stats tracker from the parent module."""
    try:
        from . import _inference_stats as stats
        return stats
    except ImportError:
        return None

from datetime import datetime
from typing import Any

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


def _safe_mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _safe_float_list(values: list[Any]) -> list[float]:
    out: list[float] = []
    for v in values:
        try:
            out.append(float(v))
        except Exception:
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


def _match_face(embedding: list[float], people: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    if not embedding or not people:
        return None
    best = None
    best_score = -1.0
    for person in people:
        p_id = person.get("id")
        p_name = person.get("name")
        for emb in person.get("embeddings", []) or []:
            if isinstance(emb, dict):
                emb = emb.get("vector", [])
            emb_list = _safe_float_list(emb)
            if not emb_list:
                continue
            score = _cosine_similarity(embedding, emb_list)
            if score > best_score:
                best_score = score
                best = {"person_id": p_id, "name": p_name, "similarity": round(float(score), 4)}
    if best and best_score >= float(threshold):
        return best
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
    except Exception:
        labels = {}

    return model_path, labels


def _build_interpreter(model_path: str, device: str):
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
            except Exception:
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


def _annotate_frame(frame_path: str, detections: list[dict[str, Any]], out_path: str) -> None:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow not available")

    img = Image.open(frame_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    for det in detections:
        box = det.get("box") or {}
        x = int(box.get("x", 0))
        y = int(box.get("y", 0))
        w = int(box.get("w", 0))
        h = int(box.get("h", 0))
        label = det.get("label", "obj")
        score = det.get("score")
        text = f"{label} {score:.2f}" if isinstance(score, (int, float)) else str(label)

        x2 = max(x + w, x + 1)
        y2 = max(y + h, y + 1)
        draw.rectangle([x, y, x2, y2], outline=(255, 64, 64), width=2)

        text_w = max(8 * len(text), 20)
        text_h = 16
        tx1, ty1 = x, max(0, y - text_h)
        tx2, ty2 = x + text_w + 6, y
        draw.rectangle([tx1, ty1, tx2, ty2], fill=(0, 0, 0))
        draw.text((tx1 + 3, ty1 + 2), text, fill=(255, 255, 255))

    img.save(out_path, "JPEG", quality=90)


async def _render_annotated_video(
    frames: list[str],
    detections: list[dict[str, Any]],
    output_dir: str,
    interval_s: int,
) -> str:
    if not frames:
        raise RuntimeError("No frames to annotate")
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow not available")

    annotated_dir = os.path.join(output_dir, "annotated")
    _safe_mkdir(annotated_dir)

    for idx, frame_path in enumerate(frames):
        dets = detections[idx].get("objects", []) if idx < len(detections) else []
        out_path = os.path.join(annotated_dir, f"frame_{idx:04d}.jpg")
        await asyncio.to_thread(_annotate_frame, frame_path, dets, out_path)

    output_video = os.path.join(output_dir, "annotated.mp4")
    fps = 1 / max(1, int(interval_s))

    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        os.path.join(annotated_dir, "frame_%04d.jpg"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        output_video,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.wait()

    if not os.path.exists(output_video):
        raise RuntimeError("Annotated video not created")
    return output_video


async def extract_frames(video_path: str, output_dir: str, interval_s: int = 2) -> list[str]:
    """Extract frames from a video using ffmpeg. Returns list of frame files."""
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
    await process.wait()

    files = sorted(
        [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.startswith("frame_")]
    )
    return files


async def analyze_recording(
    video_path: str,
    output_root: str,
    objects: list[str],
    device: str,
    interval_s: int = 2,
    perf_snapshot: dict | None = None,
    detector_url: str | None = None,
    detector_confidence: float = 0.4,
    face_enabled: bool = False,
    face_confidence: float = 0.6,
    face_match_threshold: float = 0.35,
    face_store_embeddings: bool = False,
    people_db: list[dict[str, Any]] | None = None,
    face_detector_url: str | None = None,
) -> dict:
    """Offline analysis stub: extracts frames and writes a results JSON.

    This function runs locally and prepares data for later detection.
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

    result = {
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

    result_path = os.path.join(job_dir, "result.json")
    _write_json(result_path, result)

    try:
        start_time = time.monotonic()
        frames = await extract_frames(video_path, frames_dir, interval_s)
        duration_sec = round(time.monotonic() - start_time, 2)
        result["frames"] = frames
        result["frame_count"] = len(frames)
        result["duration_sec"] = duration_sec
        result["status"] = "frames_extracted"
        _write_json(result_path, result)

        detections: list[dict[str, Any]] = []

        # Run object detection on extracted frames (optional)
        if frames and objects:
            try:
                frame_w = frame_h = None
                if detector_url:
                    async with aiohttp.ClientSession() as session:
                        for idx, frame_path in enumerate(frames):
                            with open(frame_path, "rb") as f:
                                form = aiohttp.FormData()
                                form.add_field("file", f, filename=os.path.basename(frame_path), content_type="image/jpeg")
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
                    annotated_video = await _render_annotated_video(frames, detections, job_dir, interval_s)
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

                async with aiohttp.ClientSession() as session:
                    for idx, frame_path in enumerate(frames):
                        with open(frame_path, "rb") as f:
                            frame_bytes = f.read()

                        frame_img = None
                        if Image is not None:
                            try:
                                frame_img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
                            except Exception:
                                frame_img = None

                        embed_flag = "1" if (face_store_embeddings or (people_db and len(people_db) > 0)) else "0"
                        form = aiohttp.FormData()
                        form.add_field("file", frame_bytes, filename=os.path.basename(frame_path), content_type="image/jpeg")
                        form.add_field("device", device)
                        form.add_field("confidence", str(face_confidence))
                        form.add_field("embed", embed_flag)

                        _detect_start = time.perf_counter()
                        async with session.post(f"{face_url.rstrip('/')}/faces", data=form, timeout=60) as resp:
                            if resp.status != 200:
                                raise RuntimeError(f"Face detector error {resp.status}")
                            data = await resp.json()
                        # Retry once with lower confidence if no faces found
                        if not (data.get("faces") or []) and float(face_confidence) > 0.25:
                            retry_conf = max(0.2, float(face_confidence) * 0.6)
                            form_retry = aiohttp.FormData()
                            form_retry.add_field("file", frame_bytes, filename=os.path.basename(frame_path), content_type="image/jpeg")
                            form_retry.add_field("device", device)
                            form_retry.add_field("confidence", str(retry_conf))
                            form_retry.add_field("embed", embed_flag)
                            async with session.post(f"{face_url.rstrip('/')}/faces", data=form_retry, timeout=60) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                        _detect_ms = (time.perf_counter() - _detect_start) * 1000
                        _used_device = data.get("device", device)
                        _stats = _get_inference_stats()
                        if _stats:
                            _stats.record(_used_device, _detect_ms, 1)

                        faces = data.get("faces", []) or []
                        frame_w = data.get("frame_width")
                        frame_h = data.get("frame_height")

                        # If no faces found, try person crops (helps for small faces)
                        if not faces and frame_img is not None and idx < len(detections):
                            person_boxes = [o for o in (detections[idx].get("objects") or []) if o.get("label") == "person"]
                            extra_faces = []
                            for pobj in person_boxes:
                                box = pobj.get("box") or {}
                                x = max(int(box.get("x", 0)), 0)
                                y = max(int(box.get("y", 0)), 0)
                                w = max(int(box.get("w", 0)), 1)
                                h = max(int(box.get("h", 0)), 1)
                                pad = int(0.1 * max(w, h))
                                x1 = max(x - pad, 0)
                                y1 = max(y - pad, 0)
                                x2 = min(x + w + pad, frame_img.width)
                                y2 = min(y + h + pad, frame_img.height)
                                if (x2 - x1) < 40 or (y2 - y1) < 40:
                                    continue
                                crop = frame_img.crop((x1, y1, x2, y2))

                                async def _detect_crop(img, scale_factor: float, conf: float) -> list[dict[str, Any]]:
                                    buf = io.BytesIO()
                                    img.save(buf, format="JPEG", quality=80)
                                    crop_bytes = buf.getvalue()
                                    crop_form = aiohttp.FormData()
                                    crop_form.add_field("file", crop_bytes, filename="crop.jpg", content_type="image/jpeg")
                                    crop_form.add_field("device", device)
                                    crop_form.add_field("confidence", str(conf))
                                    crop_form.add_field("embed", embed_flag)
                                    async with session.post(f"{face_url.rstrip('/')}/faces", data=crop_form, timeout=60) as resp:
                                        if resp.status != 200:
                                            return []
                                        crop_data = await resp.json()
                                    faces_out = []
                                    for cf in (crop_data.get("faces") or []):
                                        cbox = cf.get("box") or {}
                                        sx = float(cbox.get("x", 0)) / scale_factor
                                        sy = float(cbox.get("y", 0)) / scale_factor
                                        sw = float(cbox.get("w", 0)) / scale_factor
                                        sh = float(cbox.get("h", 0)) / scale_factor
                                        cf_box = {
                                            "x": int(sx) + x1,
                                            "y": int(sy) + y1,
                                            "w": int(sw),
                                            "h": int(sh),
                                        }
                                        cf["box"] = cf_box
                                        faces_out.append(cf)
                                    return faces_out

                                faces_crop = await _detect_crop(crop, 1.0, float(face_confidence))
                                if not faces_crop:
                                    max_dim = max(crop.width, crop.height)
                                    if max_dim < 160:
                                        scale_factor = 1.5
                                        crop_up = crop.resize((int(crop.width * scale_factor), int(crop.height * scale_factor)))
                                        crop_conf = max(0.15, float(face_confidence) * 0.7)
                                        faces_crop = await _detect_crop(crop_up, scale_factor, crop_conf)
                                if not faces_crop:
                                    max_dim = max(crop.width, crop.height)
                                    if max_dim < 120:
                                        scale_factor = 2.0
                                        crop_up = crop.resize((int(crop.width * scale_factor), int(crop.height * scale_factor)))
                                        crop_conf = max(0.1, float(face_confidence) * 0.6)
                                        faces_crop = await _detect_crop(crop_up, scale_factor, crop_conf)

                                if faces_crop:
                                    extra_faces.extend(faces_crop)
                            if extra_faces:
                                faces = extra_faces

                        # Note: MoveNet and head_estimate fallbacks removed to reduce false positives
                        # Only real face detection is used - this prevents ghost faces from shadows/objects

                        if frame_w and frame_h:
                            result["frame_width"] = frame_w
                            result["frame_height"] = frame_h
                        normed_faces = []
                        for face in faces:
                            face_box = face.get("box") or {}
                            score = face.get("score", 0.0)
                            emb = face.get("embedding")
                            emb_source = (face.get("embedding_source") or "").lower()
                            emb_list = _safe_float_list(emb) if isinstance(emb, list) else []
                            if emb_list:
                                emb_list = _normalize_embedding(emb_list)
                            match = None
                            # Allow matching with any embedding type (including fallback)
                            # for basic face recognition without dedicated embedding model
                            if emb_list and people_db:
                                match = _match_face(emb_list, people_db, face_match_threshold)
                                if match:
                                    faces_matched += 1

                            # HIGH-005 Fix: Limit thumbnails to prevent memory exhaustion
                            thumb_data = None
                            total_thumbs_created = sum(
                                1 for det in detections 
                                for f in det.get("faces", []) 
                                if f.get("thumb")
                            )
                            
                            if frame_img is not None and total_thumbs_created < MAX_FACES_WITH_THUMBS:
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
                                    thumb_data = f"data:image/jpeg;base64,{thumb_b64}"
                                except Exception:
                                    thumb_data = None

                            face_item = {
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
                            # Store embeddings regardless of source (including fallback)
                            # so face samples can be collected even without a dedicated embedding model
                            if emb_list and face_store_embeddings:
                                face_item["embedding"] = emb_list
                            if emb_source:
                                face_item["embedding_source"] = emb_source
                            if thumb_data:
                                face_item["thumb"] = thumb_data
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

        return result
    except asyncio.CancelledError:
        result["status"] = "cancelled"
        result["error"] = "analysis_cancelled"
        _write_json(result_path, result)
        raise
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        _write_json(result_path, result)
        return result
    finally:
        try:
            _write_json(result_path, result)
        except Exception:
            pass
