import os
import json
import urllib.request
import io
import time
import threading
from typing import List, Dict, Any, Optional

import numpy as np
from PIL import Image
from fastapi import FastAPI, UploadFile, File, Form
import tflite_runtime.interpreter as tflite

# Use Frigate's tested models (mobiledet - much better than old mobilenet)
MODEL_CPU_URL = "https://github.com/google-coral/test_data/raw/release-frogfish/ssdlite_mobiledet_coco_qat_postprocess.tflite"
MODEL_CORAL_URL = "https://github.com/google-coral/test_data/raw/release-frogfish/ssdlite_mobiledet_coco_qat_postprocess_edgetpu.tflite"
LABELS_URL = "https://github.com/google-coral/test_data/raw/master/coco_labels.txt"

MODEL_DIR = "/data/models"

# Use full path to libedgetpu (like Frigate does)
EDGETPU_LIB = "/usr/lib/x86_64-linux-gnu/libedgetpu.so.1.0"
EDGETPU_OPTIONS = {"device": "usb"}

app = FastAPI()

# ===== CACHED INTERPRETERS (Critical for Coral USB performance) =====
_interpreter_lock = threading.Lock()
_cached_interpreters: Dict[str, Any] = {}
_labels_cache: Optional[Dict[int, str]] = None
_available_devices: Optional[List[str]] = None


def _safe_mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _download_file(url: str, dest: str) -> None:
    _safe_mkdir(os.path.dirname(dest))
    if not os.path.exists(dest):
        print(f"Downloading {url} to {dest}")
        urllib.request.urlretrieve(url, dest)


def _load_labels(path: str) -> Dict[int, str]:
    labels: Dict[int, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f.readlines()):
            label = line.strip()
            if label:
                labels[i] = label
    return labels


def _detect_devices() -> List[str]:
    global _available_devices
    if _available_devices is not None:
        return _available_devices
    
    devices = ["cpu"]
    try:
        delegate = tflite.load_delegate(EDGETPU_LIB, EDGETPU_OPTIONS)
        devices.append("coral_usb")
        print("Coral USB EdgeTPU detected!")
    except Exception as e:
        print(f"Coral USB not available: {e}")
    
    _available_devices = devices
    return devices


def _get_model(device: str) -> str:
    if device == "coral_usb":
        path = os.path.join(MODEL_DIR, "ssdlite_mobiledet_coco_qat_postprocess_edgetpu.tflite")
        _download_file(MODEL_CORAL_URL, path)
        return path
    path = os.path.join(MODEL_DIR, "ssdlite_mobiledet_coco_qat_postprocess.tflite")
    _download_file(MODEL_CPU_URL, path)
    return path


def _get_labels() -> Dict[int, str]:
    global _labels_cache
    if _labels_cache is not None:
        return _labels_cache
    
    path = os.path.join(MODEL_DIR, "coco_labels.txt")
    _download_file(LABELS_URL, path)
    _labels_cache = _load_labels(path)
    return _labels_cache


def _get_cached_interpreter(device: str):
    """Get or create a cached interpreter for the device.
    
    CRITICAL: Creating a new interpreter for each request blocks the Coral USB.
    We must reuse interpreters like Frigate does.
    """
    global _cached_interpreters
    
    with _interpreter_lock:
        if device in _cached_interpreters:
            return _cached_interpreters[device]
        
        model_path = _get_model(device)
        interpreter = _build_interpreter(model_path, device)
        interpreter.allocate_tensors()
        _cached_interpreters[device] = interpreter
        print(f"Created and cached interpreter for device: {device}")
        return interpreter


def _build_interpreter(model_path: str, device: str):
    if device == "coral_usb":
        delegate = tflite.load_delegate(EDGETPU_LIB, EDGETPU_OPTIONS)
        return tflite.Interpreter(model_path=model_path, experimental_delegates=[delegate])
    return tflite.Interpreter(model_path=model_path)


def _run_detection(img_bytes: bytes, labels: Dict[int, str], device: str, confidence: float):
    """Run object detection on image bytes using CACHED interpreter.
    
    The Frigate mobiledet model outputs:
    - Output 0: Boxes [1, N, 4] - bounding boxes (ymin, xmin, ymax, xmax) normalized 0-1
    - Output 1: Classes [1, N] - class IDs
    - Output 2: Scores [1, N] - confidence scores 0-1
    - Output 3: Count [1] - number of detections (always max, filter by score)
    """
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    frame_width, frame_height = img.size

    # Use cached interpreter (critical for Coral USB performance!)
    interpreter = _get_cached_interpreter(device)

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    input_shape = input_details[0]["shape"]
    target_h, target_w = int(input_shape[1]), int(input_shape[2])
    img_resized = img.resize((target_w, target_h))
    input_data = np.expand_dims(np.array(img_resized, dtype=np.uint8), axis=0)

    interpreter.set_tensor(input_details[0]["index"], input_data)
    
    start = time.perf_counter()
    interpreter.invoke()
    inference_ms = (time.perf_counter() - start) * 1000

    # Parse outputs by index (Frigate mobiledet format)
    # 0: boxes, 1: classes, 2: scores, 3: count
    boxes = interpreter.get_tensor(output_details[0]["index"])[0]  # [N, 4]
    classes = interpreter.get_tensor(output_details[1]["index"])[0]  # [N]
    scores = interpreter.get_tensor(output_details[2]["index"])[0]  # [N]
    
    detections = []
    for i in range(len(scores)):
        score = float(scores[i])
        if score < confidence:
            continue
        cls_id = int(classes[i])
        label = labels.get(cls_id, str(cls_id))
        ymin, xmin, ymax, xmax = boxes[i]
        x = int(xmin * frame_width)
        y = int(ymin * frame_height)
        w = int((xmax - xmin) * frame_width)
        h = int((ymax - ymin) * frame_height)
        detections.append({
            "label": label,
            "score": round(score, 3),
            "box": {"x": x, "y": y, "w": w, "h": h}
        })

    return detections, frame_width, frame_height, inference_ms


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/info")
def info():
    return {
        "devices": _detect_devices(),
        "numpy": getattr(np, "__version__", None),
        "tflite_runtime": getattr(tflite, "__version__", None),
        "edgetpu_lib": EDGETPU_LIB,
    }


@app.post("/detect")
async def detect(
    file: UploadFile = File(...),
    objects: str = Form("[]"),
    device: str = Form("auto"),
    confidence: float = Form(0.4),
):
    content = await file.read()
    labels = _get_labels()
    devices = _detect_devices()

    if device == "auto":
        device = "coral_usb" if "coral_usb" in devices else "cpu"
    if device not in devices:
        device = "cpu"

    inference_ms = 0
    try:
        detections, fw, fh, inference_ms = _run_detection(content, labels, device, confidence)
    except RuntimeError as e:
        if device == "coral_usb" and "EdgeTpu" in str(e):
            device = "cpu"
            detections, fw, fh, inference_ms = _run_detection(content, labels, device, confidence)
        else:
            raise

    try:
        obj_filter = json.loads(objects or "[]")
    except Exception:
        obj_filter = []
    if obj_filter:
        detections = [d for d in detections if d["label"] in obj_filter]

    return {
        "objects": detections, 
        "frame_width": fw, 
        "frame_height": fh, 
        "device": device,
        "inference_ms": round(inference_ms, 1)
    }
