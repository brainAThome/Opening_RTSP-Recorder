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
from fastapi.middleware.cors import CORSMiddleware
import tflite_runtime.interpreter as tflite

# Use Frigate's tested models (mobiledet - much better than old mobilenet)
MODEL_CPU_URL = "https://github.com/google-coral/test_data/raw/release-frogfish/ssdlite_mobiledet_coco_qat_postprocess.tflite"
MODEL_CORAL_URL = "https://github.com/google-coral/test_data/raw/release-frogfish/ssdlite_mobiledet_coco_qat_postprocess_edgetpu.tflite"
LABELS_URL = "https://github.com/google-coral/test_data/raw/master/coco_labels.txt"

# Face Detection (EdgeTPU kompatibel)
FACE_DET_CPU_URL = "https://github.com/google-coral/test_data/raw/release-frogfish/ssd_mobilenet_v2_face_quant_postprocess.tflite"
FACE_DET_CORAL_URL = "https://github.com/google-coral/test_data/raw/release-frogfish/ssd_mobilenet_v2_face_quant_postprocess_edgetpu.tflite"

# Face Embedding (EdgeTPU kompatibel, Beispielmodell)
FACE_EMBED_CPU_URL = "https://github.com/google-coral/test_data/raw/release-frogfish/mobilefacenet.tflite"
FACE_EMBED_CORAL_URL = "https://github.com/google-coral/test_data/raw/release-frogfish/mobilefacenet_edgetpu.tflite"

MODEL_DIR = "/data/models"

# Use full path to libedgetpu (like Frigate does)
EDGETPU_LIB = "/usr/lib/x86_64-linux-gnu/libedgetpu.so.1.0"
EDGETPU_OPTIONS = {"device": "usb"}

# ===== Configuration Constants (MED-012 Fix) =====
DEFAULT_CONFIDENCE_THRESHOLD = 0.4
DEFAULT_FACE_CONFIDENCE_THRESHOLD = 0.5
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB max upload
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
# Image magic bytes for validation
IMAGE_MAGIC_BYTES = {
    b'\xff\xd8\xff': 'image/jpeg',
    b'\x89PNG': 'image/png',
    b'GIF87a': 'image/gif',
    b'GIF89a': 'image/gif',
    b'RIFF': 'image/webp',  # WebP starts with RIFF....WEBP
}
# ===== End Configuration Constants =====

app = FastAPI()

# ===== CORS Configuration (MED-009 Fix) =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to Home Assistant origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== CACHED INTERPRETERS (Critical for Coral USB performance) =====
_interpreter_lock = threading.Lock()
_cached_interpreters: Dict[str, Any] = {}
_labels_cache: Optional[Dict[int, str]] = None
_available_devices: Optional[List[str]] = None
_cached_face_det: Dict[str, Any] = {}
_cached_face_embed: Dict[str, Any] = {}
_face_embed_failed = False


# ===== Image Validation (MED-006 Fix) =====
def _validate_image_content(content: bytes, content_type: Optional[str] = None) -> tuple[bool, str]:
    """Validate that uploaded content is a valid image.
    
    Returns (is_valid, error_message).
    """
    if len(content) > MAX_IMAGE_SIZE_BYTES:
        return False, f"Image too large (max {MAX_IMAGE_SIZE_BYTES // 1024 // 1024}MB)"
    
    if len(content) < 8:
        return False, "Content too small to be a valid image"
    
    # Check magic bytes
    is_valid_magic = False
    for magic, mime in IMAGE_MAGIC_BYTES.items():
        if content[:len(magic)] == magic:
            is_valid_magic = True
            break
    
    if not is_valid_magic:
        return False, "Invalid image format (not JPEG/PNG/GIF/WebP)"
    
    # Try to actually open the image
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()  # Verify it's a valid image
    except Exception as e:
        return False, f"Invalid image data: {e}"
    
    return True, ""
# ===== End Image Validation =====


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


def _get_face_det_model(device: str) -> str:
    if device == "coral_usb":
        path = os.path.join(MODEL_DIR, "ssd_mobilenet_v2_face_quant_postprocess_edgetpu.tflite")
        _download_file(FACE_DET_CORAL_URL, path)
        return path
    path = os.path.join(MODEL_DIR, "ssd_mobilenet_v2_face_quant_postprocess.tflite")
    _download_file(FACE_DET_CPU_URL, path)
    return path


def _get_face_embed_model(device: str) -> str:
    if device == "coral_usb":
        path = os.path.join(MODEL_DIR, "mobilefacenet_edgetpu.tflite")
        _download_file(FACE_EMBED_CORAL_URL, path)
        return path
    path = os.path.join(MODEL_DIR, "mobilefacenet.tflite")
    _download_file(FACE_EMBED_CPU_URL, path)
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
    
    HIGH-004 Fix: Added error recovery for Coral USB disconnect/reconnect.
    """
    global _cached_interpreters
    
    with _interpreter_lock:
        if device in _cached_interpreters:
            # Verify interpreter is still valid (HIGH-004 Fix)
            try:
                # Quick sanity check - accessing input details should work
                _cached_interpreters[device].get_input_details()
                return _cached_interpreters[device]
            except Exception as e:
                print(f"Cached interpreter for {device} is invalid, recreating: {e}")
                del _cached_interpreters[device]
        
        try:
            model_path = _get_model(device)
            interpreter = _build_interpreter(model_path, device)
            interpreter.allocate_tensors()
            _cached_interpreters[device] = interpreter
            print(f"Created and cached interpreter for device: {device}")
            return interpreter
        except Exception as e:
            print(f"ERROR creating interpreter for {device}: {e}")
            # For Coral device errors, ensure cache is cleared for retry
            if device in _cached_interpreters:
                del _cached_interpreters[device]
            raise


def _build_interpreter(model_path: str, device: str):
    """Build TFLite interpreter with optional Coral TPU delegate.
    
    HIGH-004 Fix: Added explicit error handling for Coral device issues.
    """
    if device == "coral_usb":
        try:
            delegate = tflite.load_delegate(EDGETPU_LIB, EDGETPU_OPTIONS)
            return tflite.Interpreter(model_path=model_path, experimental_delegates=[delegate])
        except Exception as e:
            print(f"ERROR loading Coral delegate: {e}. Check if Coral USB is connected.")
            raise RuntimeError(f"Coral TPU initialization failed: {e}") from e
    return tflite.Interpreter(model_path=model_path)


def _get_cached_face_det_interpreter(device: str):
    """Get or create cached face detection interpreter.
    
    HIGH-004 Fix: Added error recovery for device disconnect.
    """
    global _cached_face_det
    with _interpreter_lock:
        if device in _cached_face_det:
            try:
                _cached_face_det[device].get_input_details()
                return _cached_face_det[device]
            except Exception as e:
                print(f"Cached face-det interpreter for {device} invalid, recreating: {e}")
                del _cached_face_det[device]
        
        try:
            model_path = _get_face_det_model(device)
            interpreter = _build_interpreter(model_path, device)
            interpreter.allocate_tensors()
            _cached_face_det[device] = interpreter
            print(f"Created and cached face-detector for device: {device}")
            return interpreter
        except Exception as e:
            print(f"ERROR creating face-det interpreter for {device}: {e}")
            if device in _cached_face_det:
                del _cached_face_det[device]
            raise


def _get_cached_face_embed_interpreter(device: str):
    """Get or create cached face embedding interpreter.
    
    HIGH-004 Fix: Added error recovery for device disconnect.
    """
    global _cached_face_embed
    with _interpreter_lock:
        if device in _cached_face_embed:
            try:
                _cached_face_embed[device].get_input_details()
                return _cached_face_embed[device]
            except Exception as e:
                print(f"Cached face-embed interpreter for {device} invalid, recreating: {e}")
                del _cached_face_embed[device]
        
        try:
            model_path = _get_face_embed_model(device)
            interpreter = _build_interpreter(model_path, device)
            interpreter.allocate_tensors()
            _cached_face_embed[device] = interpreter
            print(f"Created and cached face-embedding for device: {device}")
            return interpreter
        except Exception as e:
            print(f"ERROR creating face-embed interpreter for {device}: {e}")
            if device in _cached_face_embed:
                del _cached_face_embed[device]
            raise


def _parse_detection_outputs(output_details, outputs):
    boxes = classes = scores = None
    count = 0
    names = [(detail.get("name") or "") for detail in output_details]
    if len(outputs) >= 4 and all("TFLite_Detection_PostProcess" in name for name in names):
        boxes = outputs[0]
        classes = outputs[1]
        scores = outputs[2]
        try:
            count = int(outputs[3].reshape(-1)[0])
        except Exception:
            count = 0
        return boxes, classes, scores, count
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
    if boxes is None or scores is None:
        raise RuntimeError("Unable to parse detection outputs")
    if classes is None:
        classes = np.zeros(scores.shape, dtype=np.int32)
    if count == 0:
        count = min(boxes.shape[1], scores.shape[1], classes.shape[1])
    return boxes, classes, scores, count


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


def _to_jsonable(value: Any):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _run_face_detection(img_bytes: bytes, device: str, confidence: float):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    frame_width, frame_height = img.size

    interpreter = _get_cached_face_det_interpreter(device)
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    input_shape = input_details[0]["shape"]
    target_h, target_w = int(input_shape[1]), int(input_shape[2])
    img_resized = img.resize((target_w, target_h))

    dtype = input_details[0]["dtype"]
    quant = input_details[0].get("quantization") or (0.0, 0)
    zero_point = int(quant[1]) if len(quant) > 1 else 0
    if dtype == np.float32:
        arr = np.array(img_resized, dtype=np.float32)
        arr = (arr / 255.0)
        input_data = np.expand_dims(arr, axis=0)
    else:
        if dtype == np.int8:
            arr = np.array(img_resized, dtype=np.float32)
            arr = arr - float(zero_point)
            arr = np.clip(arr, -128, 127)
            input_data = np.expand_dims(arr.astype(np.int8), axis=0)
        else:
            input_data = np.expand_dims(np.array(img_resized, dtype=np.uint8), axis=0)

    interpreter.set_tensor(input_details[0]["index"], input_data)
    start = time.perf_counter()
    interpreter.invoke()
    inference_ms = (time.perf_counter() - start) * 1000

    outputs = [interpreter.get_tensor(d["index"]) for d in output_details]
    boxes, classes, scores, count = _parse_detection_outputs(output_details, outputs)
    max_score = None
    scores_dtype = None
    output_info = []
    input_info = []
    input_details_raw = None
    input_details_error = None
    try:
        if scores is not None:
            scores_dtype = str(scores.dtype)
            max_score = float(scores.max())
    except Exception:
        max_score = None

    try:
        input_details_raw = str(input_details)
        for d in input_details:
            if isinstance(d, dict):
                name_val = d.get("name")
                shape_val = d.get("shape")
                dtype_val = d.get("dtype")
                quant_val = d.get("quantization")
            else:
                name_val = None
                shape_val = None
                dtype_val = None
                quant_val = None
            shape_json = _to_jsonable(shape_val)
            if shape_json is None:
                shape_json = []
            info = {
                "name": _to_jsonable(name_val),
                "shape": shape_json,
                "dtype": str(dtype_val),
                "quant": _to_jsonable(quant_val),
            }
            input_info.append(info)
    except Exception as e:
        input_info = []
        input_details_raw = None
        input_details_error = str(e)

    try:
        for d, out in zip(output_details, outputs):
            output_info.append({
                "name": d.get("name"),
                "shape": list(out.shape),
                "dtype": str(out.dtype),
            })
    except Exception:
        output_info = []

    faces = []
    for i in range(int(count)):
        score = float(scores[0][i])
        if score < confidence:
            continue
        ymin, xmin, ymax, xmax = boxes[0][i]
        x = int(xmin * frame_width)
        y = int(ymin * frame_height)
        w = int((xmax - xmin) * frame_width)
        h = int((ymax - ymin) * frame_height)
        faces.append({
            "score": round(score, 3),
            "box": {"x": x, "y": y, "w": w, "h": h}
        })

    return faces, frame_width, frame_height, inference_ms, max_score, scores_dtype, output_info, input_info, input_details_raw, input_details_error


def _run_face_embedding(face_img: Image.Image, device: str):
    global _face_embed_failed

    def _fallback_embedding(img: Image.Image) -> list[float]:
        grey = img.convert("L").resize((16, 8))
        arr = np.array(grey, dtype=np.float32).reshape(-1)
        if arr.size == 0:
            return []
        arr = arr / 255.0
        mean = float(arr.mean())
        arr = arr - mean
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        return arr.astype(np.float32).tolist()

    if _face_embed_failed:
        return _fallback_embedding(face_img), 0.0, "fallback"

    try:
        interpreter = _get_cached_face_embed_interpreter(device)
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()

        input_shape = input_details[0]["shape"]
        target_h, target_w = int(input_shape[1]), int(input_shape[2])
        img_resized = face_img.resize((target_w, target_h))

        dtype = input_details[0]["dtype"]
        if dtype == np.float32:
            arr = np.array(img_resized, dtype=np.float32)
            arr = (arr / 127.5) - 1.0
            input_data = np.expand_dims(arr, axis=0)
        else:
            input_data = np.expand_dims(np.array(img_resized, dtype=np.uint8), axis=0)

        interpreter.set_tensor(input_details[0]["index"], input_data)
        start = time.perf_counter()
        interpreter.invoke()
        inference_ms = (time.perf_counter() - start) * 1000

        output = interpreter.get_tensor(output_details[0]["index"])[0]
        emb = output.astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb.tolist(), inference_ms, "model"
    except Exception:
        _face_embed_failed = True
        return _fallback_embedding(face_img), 0.0, "fallback"


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
        "face_detection": {
            "cpu_model": os.path.basename(FACE_DET_CPU_URL),
            "coral_model": os.path.basename(FACE_DET_CORAL_URL),
        },
        "face_embedding": {
            "cpu_model": os.path.basename(FACE_EMBED_CPU_URL),
            "coral_model": os.path.basename(FACE_EMBED_CORAL_URL),
        },
    }


@app.post("/detect")
async def detect(
    file: UploadFile = File(...),
    objects: str = Form("[]"),
    device: str = Form("auto"),
    confidence: float = Form(DEFAULT_CONFIDENCE_THRESHOLD),
):
    content = await file.read()
    
    # MED-006 Fix: Validate image content
    is_valid, error_msg = _validate_image_content(content, file.content_type)
    if not is_valid:
        return {"error": error_msg, "objects": [], "device": "none"}
    
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


@app.post("/faces")
async def faces(
    file: UploadFile = File(...),
    device: str = Form("auto"),
    confidence: float = Form(0.6),
    embed: str = Form("1"),
    debug: str = Form("0"),
):
    content = await file.read()
    devices = _detect_devices()

    if device == "auto":
        device = "coral_usb" if "coral_usb" in devices else "cpu"
    if device not in devices:
        device = "cpu"

    try:
        faces_list, fw, fh, inference_ms, max_score, scores_dtype, output_info, input_info, input_details_raw, input_details_error = _run_face_detection(content, device, confidence)
    except RuntimeError as e:
        if device == "coral_usb" and "EdgeTpu" in str(e):
            device = "cpu"
            faces_list, fw, fh, inference_ms, max_score, scores_dtype, output_info, input_info, input_details_raw, input_details_error = _run_face_detection(content, device, confidence)
        else:
            raise

    embed_enabled = str(embed).lower() in ("1", "true", "yes", "on")
    embed_total_ms = 0.0
    if embed_enabled and faces_list:
        img = Image.open(io.BytesIO(content)).convert("RGB")
        for face in faces_list:
            box = face.get("box") or {}
            x = max(int(box.get("x", 0)), 0)
            y = max(int(box.get("y", 0)), 0)
            w = max(int(box.get("w", 0)), 1)
            h = max(int(box.get("h", 0)), 1)
            x2 = min(x + w, fw)
            y2 = min(y + h, fh)
            crop = img.crop((x, y, x2, y2))
            try:
                emb, emb_ms, emb_source = _run_face_embedding(crop, device)
                embed_total_ms += emb_ms
                face["embedding"] = emb
                face["embedding_source"] = emb_source
            except Exception as e:
                face["embedding_error"] = str(e)

    result = {
        "faces": faces_list,
        "frame_width": fw,
        "frame_height": fh,
        "device": device,
        "inference_ms": round(inference_ms, 1),
        "embedding_ms": round(embed_total_ms, 1),
    }
    if str(debug).lower() in ("1", "true", "yes", "on"):
        result["debug"] = {
            "max_score": max_score,
            "scores_dtype": scores_dtype,
            "input_details": input_info,
            "input_details_raw": input_details_raw,
            "input_details_error": input_details_error,
            "output_details": output_info,
        }
    return result
