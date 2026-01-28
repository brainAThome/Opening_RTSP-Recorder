import asyncio
import json
import os
import time
import urllib.request
import aiohttp

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


def _parse_outputs(output_details: list[dict[str, Any]], outputs: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
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

        # Run object detection on extracted frames (optional)
        if frames and objects:
            try:
                detections = []
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
