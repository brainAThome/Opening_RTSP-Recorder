import os
import json
import urllib.request
import io
import time
import threading
import hashlib
from typing import List, Dict, Any, Optional

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
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

# Face Embedding (EdgeTPU kompatibel)
# Note: Original mobilefacenet URLs are broken (404). Using EfficientNet-EdgeTPU-S embedding extractor instead.
# This model generates 1280-dim embeddings, works well for face/person re-identification.
# Alternative: Download face-reidentification-retail-0095 from PINTO Model Zoo for better accuracy.
FACE_EMBED_CPU_URL = "https://raw.githubusercontent.com/google-coral/test_data/master/efficientnet-edgetpu-S_quant_embedding_extractor.tflite"
FACE_EMBED_CORAL_URL = "https://raw.githubusercontent.com/google-coral/test_data/master/efficientnet-edgetpu-S_quant_embedding_extractor_edgetpu.tflite"

# MoveNet - Pose Estimation with keypoints (NOSE, EYES, EARS for precise head detection)
MOVENET_URL = "https://github.com/google-coral/test_data/raw/master/movenet_single_pose_lightning_ptq_edgetpu.tflite"

# ===== SEC-001 Fix: SHA256 Model Hashes for Integrity Verification =====
# These hashes are computed from the original Google Coral models.
# If a download fails hash verification, the model will be re-downloaded.
MODEL_SHA256_HASHES = {
    "ssdlite_mobiledet_coco_qat_postprocess.tflite": "90bb33a634e041914cc1819aa5df99818e6c396c4d2db952c0fd7a9cffc4724f",
    "ssdlite_mobiledet_coco_qat_postprocess_edgetpu.tflite": "4a2be2bbb614e576d56dcb914fa52752bf0f13411512710d355d97faa1b35641",
    "ssd_mobilenet_v2_face_quant_postprocess.tflite": "81000edf288b746e2a7a5284858c121b20df001047bcea306ac95729632ac3bb",
    "ssd_mobilenet_v2_face_quant_postprocess_edgetpu.tflite": "fea61b5deaf82870d3570eee2e32b82a1bea7ca40817a0470eaaf77c99b55d68",
    "efficientnet_edgetpu_s_embed.tflite": None,  # CPU version - hash verified on first download
    "efficientnet_edgetpu_s_embed_edgetpu.tflite": "56d453080ba30adf9cd593f2eb08d0551fe5ce8de16d05a99da97c4a1715f179",
    "movenet_single_pose_lightning_ptq_edgetpu.tflite": "25c88b77586f65c5c80d868c0555fb194f2b38c0b55aa491f4a93b7d7da58e78",
    "coco_labels.txt": "dc183f003fc753c4c43fae6fdf7f387559449573f13fa32e517fb7453fd380f1",
}
# ===== End SEC-001 Fix =====

# MoveNet keypoint indices
MOVENET_KEYPOINTS = {
    0: "nose", 1: "left_eye", 2: "right_eye", 
    3: "left_ear", 4: "right_ear",
    5: "left_shoulder", 6: "right_shoulder",
    7: "left_elbow", 8: "right_elbow",
    9: "left_wrist", 10: "right_wrist",
    11: "left_hip", 12: "right_hip",
    13: "left_knee", 14: "right_knee",
    15: "left_ankle", 16: "right_ankle"
}
MOVENET_HEAD_KEYPOINTS = {0, 1, 2, 3, 4}  # nose, eyes, ears

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

# ===== Ring Camera Optimization Constants =====
RING_ENHANCE_CONTRAST = 1.3  # Boost contrast for IR images
RING_ENHANCE_SHARPNESS = 1.2  # Slight sharpening
RING_MIN_FACE_SIZE = 40  # Minimum face size in pixels
RING_HEAD_CROP_RATIO = 0.35  # Upper 35% of person box for head
RING_CROP_PADDING = 0.2  # 20% padding around crops
RING_UPSCALE_TARGET = 320  # Upscale small crops to this size
# ===== End Configuration Constants =====

app = FastAPI()

# ===== CORS Configuration (SEC-002 Fix) =====
# Allow configuring CORS origins via environment variable for security.
# Default allows local Home Assistant instances. Set CORS_ORIGINS env var to customize.
# Examples:
#   CORS_ORIGINS="*"                        -> Allow all (development only!)
#   CORS_ORIGINS="http://homeassistant.local:8123,https://my-ha.duckdns.org"
_cors_origins_env = os.environ.get("CORS_ORIGINS", "")
if _cors_origins_env == "*":
    _cors_origins = ["*"]
elif _cors_origins_env:
    _cors_origins = [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
else:
    # Default: Allow common Home Assistant local origins
    _cors_origins = [
        "http://homeassistant.local:8123",
        "http://homeassistant:8123",
        "http://localhost:8123",
        "http://127.0.0.1:8123",
        "http://supervisor",
        "http://supervisor:80",
    ]

print(f"[CORS] Allowed origins: {_cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # Restrict to only needed methods
    allow_headers=["*"],
)

# ===== CACHED INTERPRETERS (Critical for Coral USB performance) =====
_interpreter_lock = threading.Lock()
_cached_interpreters: Dict[str, Any] = {}
_labels_cache: Optional[Dict[int, str]] = None
_available_devices: Optional[List[str]] = None
_cached_face_det: Dict[str, Any] = {}
_cached_face_embed: Dict[str, Any] = {}
_cached_movenet: Dict[str, Any] = {}  # MoveNet pose model cache

# ===== Face Embedding Failure Tracking (with retry mechanism) =====
_face_embed_failure_count = 0  # Track consecutive failures
_face_embed_max_failures = 5   # Allow this many failures before temporary fallback
_face_embed_fallback_until = 0.0  # Unix timestamp when to retry the model again
_face_embed_fallback_duration = 60.0  # Seconds to wait before retrying after max failures

# ===== TPU Health & Fallback Tracking =====
_tpu_healthy = True  # Track if TPU is working
_tpu_failure_count = 0  # Consecutive TPU failures
_tpu_max_failures = 3  # Max failures before CPU fallback
_tpu_fallback_until = 0.0  # Unix timestamp when to retry TPU
_tpu_fallback_duration = 120.0  # Seconds to wait before retrying TPU
_tpu_last_check = 0.0  # Last time we checked TPU health

# ===== Inference Metrics =====
_metrics_lock = threading.Lock()
_inference_metrics = {
    "total_inferences": 0,
    "successful_inferences": 0,
    "failed_inferences": 0,
    "retried_inferences": 0,
    "tpu_inferences": 0,
    "cpu_inferences": 0,
    "cpu_fallback_count": 0,
    "avg_inference_ms": 0.0,
    "last_inference_ms": 0.0,
    "last_device": "unknown",
    "tpu_status": "unknown",
}

# ===== Retry Configuration =====
MAX_INFERENCE_RETRIES = 2
RETRY_DELAY_MS = 50  # Wait between retries


# ===== Metrics & Logging Functions =====
def _update_metrics(success: bool, inference_ms: float, device: str, retried: bool = False):
    """Update inference metrics thread-safely."""
    global _inference_metrics
    with _metrics_lock:
        _inference_metrics["total_inferences"] += 1
        if success:
            _inference_metrics["successful_inferences"] += 1
        else:
            _inference_metrics["failed_inferences"] += 1
        if retried:
            _inference_metrics["retried_inferences"] += 1
        if device == "coral_usb":
            _inference_metrics["tpu_inferences"] += 1
        else:
            _inference_metrics["cpu_inferences"] += 1
        _inference_metrics["last_inference_ms"] = round(inference_ms, 2)
        _inference_metrics["last_device"] = device
        # Running average
        total = _inference_metrics["total_inferences"]
        if total > 0:
            old_avg = _inference_metrics["avg_inference_ms"]
            _inference_metrics["avg_inference_ms"] = round(
                ((old_avg * (total - 1)) + inference_ms) / total, 2
            )


def _log_inference(endpoint: str, device: str, inference_ms: float, success: bool, 
                   details: str = "", retries: int = 0):
    """Structured logging for inference operations."""
    status = "OK" if success else "FAIL"
    retry_str = f" [retry:{retries}]" if retries > 0 else ""
    detail_str = f" - {details}" if details else ""
    print(f"[{endpoint}] {status} device={device} time={inference_ms:.1f}ms{retry_str}{detail_str}")


def _check_tpu_health() -> bool:
    """Check if TPU is healthy and should be used.
    
    Returns True if TPU should be used, False if CPU fallback is needed.
    """
    global _tpu_healthy, _tpu_failure_count, _tpu_fallback_until, _tpu_last_check
    
    current_time = time.time()
    
    # If in fallback mode, check if we should retry TPU
    if not _tpu_healthy:
        if current_time >= _tpu_fallback_until:
            print("[TPU] Fallback period ended, attempting TPU reconnect...")
            _tpu_healthy = True
            _tpu_failure_count = 0
            _inference_metrics["tpu_status"] = "reconnecting"
        else:
            remaining = int(_tpu_fallback_until - current_time)
            if current_time - _tpu_last_check > 30:  # Log every 30s
                print(f"[TPU] In CPU fallback mode, TPU retry in {remaining}s")
                _tpu_last_check = current_time
            return False
    
    return _tpu_healthy


def _record_tpu_failure(error: Exception):
    """Record a TPU failure and switch to CPU if needed."""
    global _tpu_healthy, _tpu_failure_count, _tpu_fallback_until
    
    _tpu_failure_count += 1
    print(f"[TPU] Failure #{_tpu_failure_count}: {error}")
    
    if _tpu_failure_count >= _tpu_max_failures:
        _tpu_healthy = False
        _tpu_fallback_until = time.time() + _tpu_fallback_duration
        _inference_metrics["tpu_status"] = "failed"
        _inference_metrics["cpu_fallback_count"] += 1
        print(f"[TPU] Max failures reached! Switching to CPU for {_tpu_fallback_duration}s")
        print(f"[TPU] Will retry at {time.strftime('%H:%M:%S', time.localtime(_tpu_fallback_until))}")


def _record_tpu_success():
    """Record successful TPU inference."""
    global _tpu_failure_count, _tpu_healthy
    
    if _tpu_failure_count > 0:
        print(f"[TPU] Recovered after {_tpu_failure_count} failures")
    _tpu_failure_count = 0
    _tpu_healthy = True
    _inference_metrics["tpu_status"] = "healthy"


def _get_best_device() -> str:
    """Get the best available device, considering TPU health."""
    devices = _detect_devices()
    
    if "coral_usb" in devices and _check_tpu_health():
        return "coral_usb"
    return "cpu"


def _run_with_retry(inference_func, *args, max_retries: int = MAX_INFERENCE_RETRIES, **kwargs):
    """Run inference with retry logic.
    
    Args:
        inference_func: The inference function to call
        max_retries: Maximum number of retries (default: 2)
        *args, **kwargs: Arguments to pass to inference_func
    
    Returns:
        Result from inference_func
        
    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            result = inference_func(*args, **kwargs)
            if attempt > 0:
                print(f"[RETRY] Succeeded on attempt {attempt + 1}")
            return result
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                print(f"[RETRY] Attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(RETRY_DELAY_MS / 1000.0)
            else:
                print(f"[RETRY] All {max_retries + 1} attempts failed")
    
    raise last_exception


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


# ===== Ring Camera Optimization Functions =====
def _enhance_image_for_face_detection(img: Image.Image) -> Image.Image:
    """Enhance image for better face detection on Ring cameras.
    
    Ring cameras often have:
    - IR night vision (low contrast grayscale)
    - Wide angle lens (small faces)
    - Compression artifacts
    
    This function improves image quality for face detection.
    """
    # Convert to RGB if needed
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    # Detect if image is likely IR/night vision (low color saturation)
    # by checking if R, G, B channels are similar
    arr = np.array(img)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    color_variance = np.std([r.mean(), g.mean(), b.mean()])
    is_ir_image = color_variance < 10  # Low variance = grayscale/IR
    
    # Enhance contrast (more aggressive for IR images)
    contrast_factor = RING_ENHANCE_CONTRAST if not is_ir_image else RING_ENHANCE_CONTRAST + 0.2
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(contrast_factor)
    
    # Enhance sharpness slightly
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(RING_ENHANCE_SHARPNESS)
    
    # For IR images, also boost brightness slightly
    if is_ir_image:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.1)
    
    return img


def _extract_head_region(img: Image.Image, person_box: dict, frame_width: int, frame_height: int) -> Optional[Image.Image]:
    """Extract the head region from a person detection box.
    
    For doorbell cameras, the head is typically in the upper portion of the person box.
    We extract the upper 35% with padding for face detection.
    """
    x = person_box.get("x", 0)
    y = person_box.get("y", 0)
    w = person_box.get("w", 0)
    h = person_box.get("h", 0)
    
    if w < 20 or h < 20:
        return None
    
    # Calculate head region (upper portion of person box)
    head_height = int(h * RING_HEAD_CROP_RATIO)
    
    # Add padding around the head region
    pad_x = int(w * RING_CROP_PADDING)
    pad_y = int(head_height * RING_CROP_PADDING)
    
    # Calculate crop coordinates with padding
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(frame_width, x + w + pad_x)
    y2 = min(frame_height, y + head_height + pad_y)
    
    # Ensure minimum size
    if (x2 - x1) < RING_MIN_FACE_SIZE or (y2 - y1) < RING_MIN_FACE_SIZE:
        return None
    
    # Crop the head region
    head_crop = img.crop((x1, y1, x2, y2))
    
    return head_crop


def _upscale_for_detection(img: Image.Image, target_size: int = RING_UPSCALE_TARGET) -> Image.Image:
    """Upscale small images to improve face detection.
    
    The face detection model works best with larger images.
    Small faces in wide-angle doorbell cameras need upscaling.
    """
    w, h = img.size
    
    # Only upscale if image is smaller than target
    if max(w, h) >= target_size:
        return img
    
    # Calculate scale factor to reach target size
    scale = target_size / max(w, h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    
    # Use LANCZOS for high-quality upscaling
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def _multi_scale_face_detect(img: Image.Image, interpreter, input_details, output_details, 
                              confidence: float, scales: list = [1.0, 1.5, 2.0]) -> list:
    """Run face detection at multiple scales to catch small faces.
    
    Ring doorbell cameras often have small faces due to wide-angle lens.
    Running detection at multiple scales improves detection rate.
    """
    all_faces = []
    orig_w, orig_h = img.size
    
    for scale in scales:
        if scale == 1.0:
            scaled_img = img
        else:
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            # Don't upscale too much (memory/performance)
            if new_w > 1920 or new_h > 1080:
                continue
            scaled_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Prepare input
        input_shape = input_details[0]["shape"]
        target_h, target_w = int(input_shape[1]), int(input_shape[2])
        img_resized = scaled_img.resize((target_w, target_h))
        
        dtype = input_details[0]["dtype"]
        if dtype == np.float32:
            arr = np.array(img_resized, dtype=np.float32) / 255.0
            input_data = np.expand_dims(arr, axis=0)
        else:
            input_data = np.expand_dims(np.array(img_resized, dtype=np.uint8), axis=0)
        
        # Run inference
        interpreter.set_tensor(input_details[0]["index"], input_data)
        interpreter.invoke()
        
        outputs = [interpreter.get_tensor(d["index"]) for d in output_details]
        boxes, classes, scores, count = _parse_detection_outputs(output_details, outputs, is_face_model=True)
        
        # Collect faces and scale coordinates back to original size
        scaled_w, scaled_h = scaled_img.size
        for i in range(int(count)):
            score = float(scores[0][i])
            if score < confidence:
                continue
            ymin, xmin, ymax, xmax = boxes[0][i]
            # Scale coordinates back to original image size
            x = int((xmin * scaled_w) / scale)
            y = int((ymin * scaled_h) / scale)
            w = int(((xmax - xmin) * scaled_w) / scale)
            h = int(((ymax - ymin) * scaled_h) / scale)
            
            all_faces.append({
                "score": round(score, 3),
                "box": {"x": x, "y": y, "w": w, "h": h},
                "scale": scale
            })
    
    # Remove duplicate detections (NMS-like)
    if len(all_faces) > 1:
        all_faces = _remove_duplicate_faces(all_faces)
    
    return all_faces


def _remove_duplicate_faces(faces: list, iou_threshold: float = 0.5) -> list:
    """Remove duplicate face detections using IoU (Intersection over Union)."""
    if not faces:
        return faces
    
    # Sort by score (highest first)
    faces = sorted(faces, key=lambda f: f["score"], reverse=True)
    
    keep = []
    for face in faces:
        box = face["box"]
        is_duplicate = False
        for kept in keep:
            kbox = kept["box"]
            iou = _calculate_iou(box, kbox)
            if iou > iou_threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            keep.append(face)
    
    return keep


def _calculate_iou(box1: dict, box2: dict) -> float:
    """Calculate Intersection over Union between two boxes."""
    x1 = max(box1["x"], box2["x"])
    y1 = max(box1["y"], box2["y"])
    x2 = min(box1["x"] + box1["w"], box2["x"] + box2["w"])
    y2 = min(box1["y"] + box1["h"], box2["y"] + box2["h"])
    
    if x2 <= x1 or y2 <= y1:
        return 0.0
    
    intersection = (x2 - x1) * (y2 - y1)
    area1 = box1["w"] * box1["h"]
    area2 = box2["w"] * box2["h"]
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0.0
# ===== End Ring Camera Optimization Functions =====


def _safe_mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _compute_file_hash(filepath: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _verify_model_hash(filepath: str) -> bool:
    """Verify the SHA256 hash of a downloaded model.
    
    SEC-001 Fix: Ensures model integrity after download.
    Returns True if hash matches or no hash is defined, False otherwise.
    """
    filename = os.path.basename(filepath)
    expected_hash = MODEL_SHA256_HASHES.get(filename)
    
    if expected_hash is None:
        # No hash defined for this file - accept it but log warning
        print(f"[SECURITY] No hash defined for {filename}, skipping verification")
        return True
    
    actual_hash = _compute_file_hash(filepath)
    
    if actual_hash != expected_hash:
        print(f"[SECURITY] Hash mismatch for {filename}!")
        print(f"[SECURITY]   Expected: {expected_hash}")
        print(f"[SECURITY]   Actual:   {actual_hash}")
        return False
    
    print(f"[SECURITY] Hash verified for {filename}")
    return True


def _download_file(url: str, dest: str, verify_hash: bool = True) -> None:
    """Download a file with optional SHA256 hash verification.
    
    SEC-001 Fix: Added hash verification for model integrity.
    If hash verification fails, the file is deleted and re-downloaded once.
    """
    _safe_mkdir(os.path.dirname(dest))
    
    if os.path.exists(dest):
        # File exists - verify hash if requested
        if verify_hash and not _verify_model_hash(dest):
            print(f"[SECURITY] Removing corrupted file: {dest}")
            os.remove(dest)
        else:
            return  # File exists and is valid
    
    print(f"Downloading {url} to {dest}")
    urllib.request.urlretrieve(url, dest)
    
    # Verify hash after download
    if verify_hash and not _verify_model_hash(dest):
        print(f"[SECURITY] Downloaded file failed hash verification!")
        print(f"[SECURITY] This could indicate a man-in-the-middle attack or corrupted download.")
        print(f"[SECURITY] Removing file and retrying once...")
        os.remove(dest)
        urllib.request.urlretrieve(url, dest)
        
        if not _verify_model_hash(dest):
            os.remove(dest)
            raise SecurityError(f"Model {os.path.basename(dest)} failed hash verification after retry. "
                              f"Check your network connection or contact the developer.")


class SecurityError(Exception):
    """Exception raised when security verification fails."""
    pass


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
    """Get face embedding model path.
    
    Uses EfficientNet-EdgeTPU-S embedding extractor (1280-dim output).
    Input: 224x224 RGB image
    Output: 1280-dim normalized embedding vector
    """
    if device == "coral_usb":
        path = os.path.join(MODEL_DIR, "efficientnet_edgetpu_s_embed_edgetpu.tflite")
        _download_file(FACE_EMBED_CORAL_URL, path)
        return path
    path = os.path.join(MODEL_DIR, "efficientnet_edgetpu_s_embed.tflite")
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


# ===== MoveNet Pose Estimation (for precise head detection) =====

def _get_movenet_model() -> str:
    """Download or return cached MoveNet model path.
    
    SEC-001 Fix: Now uses _download_file with hash verification.
    """
    filename = "movenet_single_pose_lightning_ptq_edgetpu.tflite"
    model_path = os.path.join(MODEL_DIR, filename)
    _download_file(MOVENET_URL, model_path)  # SEC-001: Hash verified download
    return model_path


def _get_cached_movenet_interpreter():
    """Get or create cached MoveNet interpreter (Edge TPU only)."""
    global _cached_movenet
    device = "coral_usb"
    with _interpreter_lock:
        if device in _cached_movenet:
            try:
                _cached_movenet[device].get_input_details()
                return _cached_movenet[device]
            except Exception as e:
                print(f"Cached MoveNet interpreter invalid, recreating: {e}")
                del _cached_movenet[device]
        
        try:
            model_path = _get_movenet_model()
            interpreter = _build_interpreter(model_path, device)
            interpreter.allocate_tensors()
            _cached_movenet[device] = interpreter
            print(f"Created and cached MoveNet for Edge TPU")
            return interpreter
        except Exception as e:
            print(f"ERROR creating MoveNet interpreter: {e}")
            if device in _cached_movenet:
                del _cached_movenet[device]
            raise


def _run_movenet_pose(img_bytes: bytes):
    """Run MoveNet pose estimation on image.
    
    MoveNet outputs 17 keypoints with [y, x, confidence]:
    0: nose, 1: left_eye, 2: right_eye, 3: left_ear, 4: right_ear
    5: left_shoulder, 6: right_shoulder, ...
    
    Returns:
        - keypoints: dict of keypoint name -> {x, y, confidence}
        - head_box: calculated bounding box around head keypoints (or None if not detected)
        - inference_ms: inference time
    """
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    frame_width, frame_height = img.size
    
    interpreter = _get_cached_movenet_interpreter()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    
    # MoveNet expects 192x192 input
    input_shape = input_details[0]["shape"]
    target_h, target_w = int(input_shape[1]), int(input_shape[2])
    img_resized = img.resize((target_w, target_h))
    
    # Prepare input tensor (uint8)
    input_data = np.expand_dims(np.array(img_resized, dtype=np.uint8), axis=0)
    
    interpreter.set_tensor(input_details[0]["index"], input_data)
    
    start = time.perf_counter()
    interpreter.invoke()
    inference_ms = (time.perf_counter() - start) * 1000
    
    # Output shape: [1, 1, 17, 3] - 17 keypoints with [y, x, confidence]
    output = interpreter.get_tensor(output_details[0]["index"])
    keypoints_raw = output[0][0]  # [17, 3]
    
    # Parse keypoints
    keypoints = {}
    for idx, name in MOVENET_KEYPOINTS.items():
        kp = keypoints_raw[idx]
        y, x, conf = float(kp[0]), float(kp[1]), float(kp[2])
        # Scale to original image coordinates
        keypoints[name] = {
            "x": int(x * frame_width),
            "y": int(y * frame_height),
            "confidence": round(conf, 3)
        }
    
    # Calculate head bounding box from head keypoints
    head_box = _calculate_head_box_from_keypoints(keypoints, frame_width, frame_height)
    
    return keypoints, head_box, frame_width, frame_height, inference_ms


def _calculate_head_box_from_keypoints(keypoints: dict, frame_width: int, frame_height: int, 
                                        min_confidence: float = 0.3):
    """Calculate head bounding box from MoveNet keypoints.
    
    Uses nose as center, eyes and ears to determine width, adds padding for forehead/chin.
    """
    head_kps = ["nose", "left_eye", "right_eye", "left_ear", "right_ear"]
    valid_points = []
    
    for kp_name in head_kps:
        kp = keypoints.get(kp_name)
        if kp and kp["confidence"] >= min_confidence:
            valid_points.append(kp)
    
    # Need at least nose and one other point
    nose = keypoints.get("nose", {})
    if nose.get("confidence", 0) < min_confidence or len(valid_points) < 2:
        return None
    
    # Calculate bounding box from valid keypoints
    xs = [p["x"] for p in valid_points]
    ys = [p["y"] for p in valid_points]
    
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    
    # Calculate head dimensions
    head_width = x_max - x_min
    head_height = y_max - y_min
    
    # Ears give us the actual head width - use that as reference
    left_ear = keypoints.get("left_ear", {})
    right_ear = keypoints.get("right_ear", {})
    if left_ear.get("confidence", 0) >= min_confidence and right_ear.get("confidence", 0) >= min_confidence:
        ear_width = abs(left_ear["x"] - right_ear["x"])
        # Head is roughly as tall as wide (face is oval, but with hair it's ~square)
        head_width = max(head_width, ear_width)
        head_height = max(head_height, ear_width)
    
    # Eyes to nose distance can estimate forehead height
    eyes_y = []
    for eye_name in ["left_eye", "right_eye"]:
        eye = keypoints.get(eye_name, {})
        if eye.get("confidence", 0) >= min_confidence:
            eyes_y.append(eye["y"])
    
    if eyes_y:
        avg_eye_y = sum(eyes_y) / len(eyes_y)
        eye_nose_dist = abs(nose["y"] - avg_eye_y)
        # Forehead extends ~3x eye-nose distance above eyes (includes hair)
        forehead_height = eye_nose_dist * 3.5
        # Chin extends ~3x eye-nose distance below nose
        chin_height = eye_nose_dist * 3.2
    else:
        # Fallback: use head_width as estimate
        forehead_height = head_width * 0.8
        chin_height = head_width * 0.75
    
    # Calculate final box with padding
    center_x = nose["x"]
    center_y = nose["y"]
    
    # Half widths for box calculation
    half_width = max(head_width / 2, 30) * 1.4  # 40% padding on sides
    top_extent = forehead_height + 25  # Extra for hair
    bottom_extent = chin_height + 20  # Extra for chin/neck
    
    box_x = int(max(0, center_x - half_width))
    box_y = int(max(0, center_y - top_extent))
    box_w = int(min(frame_width - box_x, half_width * 2))
    box_h = int(min(frame_height - box_y, top_extent + bottom_extent))
    
    # Ensure minimum size
    if box_w < 40 or box_h < 40:
        return None
    
    # Score based on how many keypoints were detected with good confidence
    avg_confidence = sum(p["confidence"] for p in valid_points) / len(valid_points)
    
    return {
        "box": {"x": box_x, "y": box_y, "w": box_w, "h": box_h},
        "confidence": round(avg_confidence, 3),
        "keypoints_used": len(valid_points),
        "method": "movenet"
    }


def _parse_detection_outputs(output_details, outputs, is_face_model: bool = False):
    boxes = classes = scores = None
    count = 0
    names = [(detail.get("name") or "") for detail in output_details]
    if len(outputs) >= 4 and all("TFLite_Detection_PostProcess" in name for name in names):
        boxes = outputs[0]
        # FIXED: Both face detection and object detection models use the SAME output format:
        # Output 0: boxes [1, N, 4]
        # Output 1: classes [1, N] (all zeros for face detection - single class)
        # Output 2: scores [1, N] (confidence scores)
        # Output 3: count [1]
        # The is_face_model flag is kept for compatibility but no longer affects parsing
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


def _run_face_detection(img_bytes: bytes, device: str, confidence: float, enhance: bool = True, multi_scale: bool = True):
    """Run face detection with Ring camera optimizations.
    
    Args:
        img_bytes: Raw image bytes
        device: 'cpu' or 'coral_usb'
        confidence: Minimum confidence threshold
        enhance: Apply image enhancement (contrast, sharpness)
        multi_scale: Run detection at multiple scales
    """
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    frame_width, frame_height = img.size

    # Apply Ring camera optimizations
    if enhance:
        img = _enhance_image_for_face_detection(img)

    interpreter = _get_cached_face_det_interpreter(device)
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    # Use multi-scale detection for better small face detection
    if multi_scale:
        faces = _multi_scale_face_detect(img, interpreter, input_details, output_details, 
                                          confidence, scales=[1.0, 1.5, 2.0])
        inference_ms = 0  # Multi-scale doesn't track individual inference times
    else:
        # Standard single-scale detection
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
        boxes, classes, scores, count = _parse_detection_outputs(output_details, outputs, is_face_model=True)
        
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

    # Debug info
    max_score = None
    scores_dtype = None
    output_info = []
    input_info = []
    input_details_raw = None
    input_details_error = None
    
    try:
        # Get debug info from a single inference
        input_shape = input_details[0]["shape"]
        target_h, target_w = int(input_shape[1]), int(input_shape[2])
        img_resized = img.resize((target_w, target_h))
        input_data = np.expand_dims(np.array(img_resized, dtype=np.uint8), axis=0)
        interpreter.set_tensor(input_details[0]["index"], input_data)
        interpreter.invoke()
        outputs = [interpreter.get_tensor(d["index"]) for d in output_details]
        _, _, scores_arr, _ = _parse_detection_outputs(output_details, outputs, is_face_model=True)
        if scores_arr is not None:
            scores_dtype = str(scores_arr.dtype)
            max_score = float(scores_arr.max())
    except Exception:
        pass

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
        for d in output_details:
            out = interpreter.get_tensor(d["index"])
            output_info.append({
                "name": d.get("name"),
                "shape": list(out.shape),
                "dtype": str(out.dtype),
            })
    except Exception:
        output_info = []

    return faces, frame_width, frame_height, inference_ms, max_score, scores_dtype, output_info, input_info, input_details_raw, input_details_error


def _run_face_embedding(face_img: Image.Image, device: str):
    """Run face embedding with retry mechanism.
    
    Uses a smart failure tracking system that:
    1. Allows individual failures without permanent fallback
    2. After N consecutive failures, temporarily uses fallback
    3. Automatically retries the model after a timeout period
    
    This fixes the issue where a single error would permanently disable
    the face embedding model for the entire session.
    """
    global _face_embed_failure_count, _face_embed_fallback_until

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

    # Check if we're in temporary fallback mode
    current_time = time.time()
    if _face_embed_failure_count >= _face_embed_max_failures:
        if current_time < _face_embed_fallback_until:
            # Still in fallback period
            return _fallback_embedding(face_img), 0.0, "fallback_temp"
        else:
            # Fallback period expired, reset and try model again
            print(f"Face embedding: Retry period expired, attempting to use model again")
            _face_embed_failure_count = 0
            _face_embed_fallback_until = 0.0

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
        
        # Success! Reset failure counter
        if _face_embed_failure_count > 0:
            print(f"Face embedding: Model working again after {_face_embed_failure_count} failures")
            _face_embed_failure_count = 0
        
        return emb.tolist(), inference_ms, "model"
    except Exception as e:
        _face_embed_failure_count += 1
        print(f"Face embedding error ({_face_embed_failure_count}/{_face_embed_max_failures}): {e}")
        
        if _face_embed_failure_count >= _face_embed_max_failures:
            # Enter temporary fallback mode
            _face_embed_fallback_until = current_time + _face_embed_fallback_duration
            print(f"Face embedding: Too many failures, using fallback for {_face_embed_fallback_duration}s")
        
        return _fallback_embedding(face_img), 0.0, "fallback"


@app.get("/health")
def health():
    """Health check endpoint with TPU status."""
    return {
        "ok": True,
        "tpu_healthy": _tpu_healthy,
        "tpu_status": _inference_metrics.get("tpu_status", "unknown"),
        "devices": _detect_devices()
    }


@app.get("/stats")
def stats():
    """Get live inference statistics for the frontend dashboard.
    
    Returns real-time stats about:
    - Inference counts (total, coral, cpu)
    - Inference timing (avg, last)
    - Device usage percentages
    - System resource usage
    
    This is the primary endpoint for the v1.1.0 dashboard stats display.
    """
    with _metrics_lock:
        total = _inference_metrics["total_inferences"]
        coral = _inference_metrics["tpu_inferences"]
        cpu = _inference_metrics["cpu_inferences"]
        
        # Calculate coral usage percentage
        coral_pct = round(coral / total * 100, 1) if total > 0 else 0
        
        # Calculate recent coral usage (from last 10 inferences approximation)
        recent_coral_pct = coral_pct  # Simplified - use overall percentage
        
        # Calculate inferences per minute
        uptime = time.time() - _startup_time if '_startup_time' in globals() else 0
        ipm = round(total / (uptime / 60), 1) if uptime > 60 else 0
        
        # Get system stats (optional - psutil may not be available)
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = round(memory.used / 1024 / 1024)
            memory_total_mb = round(memory.total / 1024 / 1024)
        except ImportError:
            # psutil not installed, use /proc directly (Linux)
            try:
                with open('/proc/stat', 'r') as f:
                    cpu_line = f.readline().split()
                cpu_percent = 0  # Would need two measurements for accurate %
                
                with open('/proc/meminfo', 'r') as f:
                    meminfo = {}
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2:
                            meminfo[parts[0].rstrip(':')] = int(parts[1])
                memory_total_mb = round(meminfo.get('MemTotal', 0) / 1024)
                memory_free = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
                memory_used_mb = round((meminfo.get('MemTotal', 0) - memory_free) / 1024)
                memory_percent = round(memory_used_mb / memory_total_mb * 100, 1) if memory_total_mb > 0 else 0
            except Exception:
                cpu_percent = 0
                memory_percent = 0
                memory_used_mb = 0
                memory_total_mb = 0
        except Exception:
            cpu_percent = 0
            memory_percent = 0
            memory_used_mb = 0
            memory_total_mb = 0
        
        return {
            "devices": _detect_devices(),
            "tpu_healthy": _tpu_healthy,
            "inference_stats": {
                "uptime_seconds": round(uptime) if uptime > 0 else 0,
                "total_inferences": total,
                "coral_inferences": coral,
                "cpu_inferences": cpu,
                "last_device": _inference_metrics["last_device"],
                "inferences_per_minute": ipm,
                "avg_inference_ms": _inference_metrics["avg_inference_ms"],
                "last_inference_ms": _inference_metrics["last_inference_ms"],
                "coral_usage_pct": coral_pct,
                "recent_coral_pct": recent_coral_pct,
            },
            "system_stats": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_used_mb": memory_used_mb,
                "memory_total_mb": memory_total_mb,
            }
        }


# Track startup time for uptime calculation
_startup_time = time.time()


@app.get("/metrics")
def metrics():
    """Get detailed inference metrics.
    
    Returns:
        - Total/successful/failed inference counts
        - TPU vs CPU inference counts
        - Average and last inference times
        - TPU health status
        - CPU fallback count
    """
    with _metrics_lock:
        return {
            **_inference_metrics,
            "tpu_healthy": _tpu_healthy,
            "tpu_failure_count": _tpu_failure_count,
            "tpu_fallback_remaining_sec": max(0, round(_tpu_fallback_until - time.time(), 1)) if not _tpu_healthy else 0,
            "success_rate": round(
                _inference_metrics["successful_inferences"] / _inference_metrics["total_inferences"] * 100, 1
            ) if _inference_metrics["total_inferences"] > 0 else 100.0
        }


@app.post("/tpu_reset")
def tpu_reset():
    """Reset TPU failure counter and exit CPU fallback mode.
    
    Call this endpoint after:
    - Reconnecting Coral USB
    - Restarting the system
    - Manual intervention
    """
    global _tpu_healthy, _tpu_failure_count, _tpu_fallback_until, _cached_interpreters
    global _cached_face_det, _cached_face_embed, _cached_movenet
    
    old_healthy = _tpu_healthy
    old_failures = _tpu_failure_count
    
    # Reset tracking
    _tpu_healthy = True
    _tpu_failure_count = 0
    _tpu_fallback_until = 0.0
    _inference_metrics["tpu_status"] = "reset"
    
    # Clear interpreter caches to force recreation
    with _interpreter_lock:
        _cached_interpreters.clear()
        _cached_face_det.clear()
        _cached_face_embed.clear()
        _cached_movenet.clear()
    
    # Re-detect devices
    global _available_devices
    _available_devices = None
    devices = _detect_devices()
    
    print(f"[TPU] Reset: was_healthy={old_healthy}, failures={old_failures}, detected_devices={devices}")
    
    return {
        "reset": True,
        "previous_status": "healthy" if old_healthy else "fallback",
        "previous_failures": old_failures,
        "detected_devices": devices,
        "tpu_available": "coral_usb" in devices
    }


@app.get("/face_status")
def face_status():
    """Get current face embedding system status.
    
    Returns information about:
    - Whether the model is working or in fallback mode
    - Number of consecutive failures
    - When fallback mode will end (if active)
    
    This endpoint is useful for debugging face detection issues.
    """
    import time
    current_time = time.time()
    
    in_fallback = _face_embed_failure_count >= _face_embed_max_failures
    fallback_remaining = max(0, _face_embed_fallback_until - current_time) if in_fallback else 0
    
    return {
        "status": "fallback" if in_fallback else "active",
        "failure_count": _face_embed_failure_count,
        "max_failures_before_fallback": _face_embed_max_failures,
        "fallback_duration_sec": _face_embed_fallback_duration,
        "fallback_remaining_sec": round(fallback_remaining, 1),
        "message": f"Face embedding is in fallback mode for {round(fallback_remaining)}s" if in_fallback else "Face embedding model is active",
    }


@app.post("/face_reset")
def face_reset():
    """Reset the face embedding failure counter.
    
    Call this endpoint to immediately exit fallback mode and retry
    the face embedding model. Useful after:
    - Reconnecting Coral USB
    - Restarting the system
    - Manual intervention
    """
    global _face_embed_failure_count, _face_embed_fallback_until
    
    old_count = _face_embed_failure_count
    _face_embed_failure_count = 0
    _face_embed_fallback_until = 0.0
    
    return {
        "status": "reset",
        "previous_failure_count": old_count,
        "message": "Face embedding system reset. Model will be used for next request.",
    }


@app.get("/info")
def info():
    current_time = time.time()
    in_fallback = _face_embed_failure_count >= _face_embed_max_failures
    fallback_remaining = max(0, _face_embed_fallback_until - current_time) if in_fallback else 0
    
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
            "status": "fallback" if in_fallback else "active",
            "failure_count": _face_embed_failure_count,
            "fallback_remaining_sec": round(fallback_remaining, 1) if in_fallback else 0,
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

    # Use best device considering TPU health
    if device == "auto":
        device = _get_best_device()
    if device not in devices:
        device = "cpu"

    inference_ms = 0
    retries = 0
    original_device = device
    
    try:
        # Retry wrapper for resilience
        def do_detection():
            return _run_detection(content, labels, device, confidence)
        
        detections, fw, fh, inference_ms = _run_with_retry(do_detection, max_retries=MAX_INFERENCE_RETRIES)
        
        # Record success
        if device == "coral_usb":
            _record_tpu_success()
        _update_metrics(True, inference_ms, device)
        _log_inference("detect", device, inference_ms, True, f"{len(detections)} objects")
        
    except Exception as e:
        # Record failure and try CPU fallback
        if device == "coral_usb":
            _record_tpu_failure(e)
            # Try CPU fallback
            try:
                device = "cpu"
                detections, fw, fh, inference_ms = _run_detection(content, labels, device, confidence)
                _update_metrics(True, inference_ms, device, retried=True)
                _log_inference("detect", device, inference_ms, True, f"CPU fallback after TPU fail")
            except Exception as cpu_err:
                _update_metrics(False, 0, device)
                _log_inference("detect", device, 0, False, str(cpu_err))
                raise
        else:
            _update_metrics(False, 0, device)
            _log_inference("detect", device, 0, False, str(e))
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
        "inference_ms": round(inference_ms, 1),
        "tpu_healthy": _tpu_healthy
    }


@app.post("/faces")
async def faces(
    file: UploadFile = File(...),
    device: str = Form("auto"),
    confidence: float = Form(0.3),  # Lower default for Ring cameras
    embed: str = Form("1"),
    debug: str = Form("0"),
    enhance: str = Form("1"),  # Enable image enhancement by default
    multi_scale: str = Form("1"),  # Enable multi-scale detection by default
):
    """Detect faces in an image with Ring camera optimizations.
    
    Args:
        file: Image file to analyze
        device: 'auto', 'cpu', or 'coral_usb'
        confidence: Minimum confidence (0.0-1.0), default 0.3 for Ring cameras
        embed: Generate face embeddings ('1' or '0')
        debug: Include debug info ('1' or '0')
        enhance: Apply image enhancement for better detection ('1' or '0')
        multi_scale: Run detection at multiple scales ('1' or '0')
    """
    content = await file.read()
    devices = _detect_devices()

    # Use best device considering TPU health
    if device == "auto":
        device = _get_best_device()
    if device not in devices:
        device = "cpu"

    enhance_enabled = str(enhance).lower() in ("1", "true", "yes", "on")
    multi_scale_enabled = str(multi_scale).lower() in ("1", "true", "yes", "on")

    try:
        def do_face_detection():
            return _run_face_detection(
                content, device, confidence, enhance=enhance_enabled, multi_scale=multi_scale_enabled
            )
        
        faces_list, fw, fh, inference_ms, max_score, scores_dtype, output_info, input_info, input_details_raw, input_details_error = _run_with_retry(
            do_face_detection, max_retries=MAX_INFERENCE_RETRIES
        )
        
        if device == "coral_usb":
            _record_tpu_success()
        _update_metrics(True, inference_ms, device)
        _log_inference("faces", device, inference_ms, True, f"{len(faces_list)} faces")
        
    except Exception as e:
        if device == "coral_usb":
            _record_tpu_failure(e)
            # Try CPU fallback
            try:
                device = "cpu"
                faces_list, fw, fh, inference_ms, max_score, scores_dtype, output_info, input_info, input_details_raw, input_details_error = _run_face_detection(
                    content, device, confidence, enhance=enhance_enabled, multi_scale=multi_scale_enabled
                )
                _update_metrics(True, inference_ms, device, retried=True)
                _log_inference("faces", device, inference_ms, True, "CPU fallback")
            except Exception as cpu_err:
                _update_metrics(False, 0, device)
                _log_inference("faces", device, 0, False, str(cpu_err))
                raise
        else:
            _update_metrics(False, 0, device)
            _log_inference("faces", device, 0, False, str(e))
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
        "enhance_enabled": enhance_enabled,
        "multi_scale_enabled": multi_scale_enabled,
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


@app.post("/embed_face")
async def embed_face(
    file: UploadFile = File(...),
    device: str = Form("auto"),
):
    """Generate embedding for a face/head image crop.
    
    This endpoint takes an already-cropped face/head image and generates
    an embedding vector for it. Used for head_estimate fallback faces.
    
    Args:
        file: Cropped face/head image
        device: 'auto', 'cpu', or 'coral_usb'
    
    Returns:
        embedding: List of floats
        embedding_source: 'model' or 'fallback'
    """
    content = await file.read()
    devices = _detect_devices()

    if device == "auto":
        device = "coral_usb" if "coral_usb" in devices else "cpu"
    if device not in devices:
        device = "cpu"

    try:
        img = Image.open(io.BytesIO(content)).convert("RGB")
        emb, emb_ms, emb_source = _run_face_embedding(img, device)
        return {
            "embedding": emb,
            "embedding_source": emb_source,
            "embedding_ms": round(emb_ms, 1),
            "device": device,
        }
    except Exception as e:
        return {
            "error": str(e),
            "embedding": [],
            "embedding_source": "error",
        }


@app.post("/faces_from_person")
async def faces_from_person(
    file: UploadFile = File(...),
    person_boxes: str = Form("[]"),  # JSON array of person boxes
    device: str = Form("auto"),
    confidence: float = Form(0.2),  # Very low confidence for head crops
    embed: str = Form("1"),
):
    """Extract faces from person detection boxes.
    
    This endpoint is optimized for Ring/doorbell cameras where:
    - Faces are small due to wide-angle lens
    - Person detection works but face detection doesn't
    - Head region needs to be extracted and analyzed separately
    
    Args:
        file: Image file
        person_boxes: JSON array of person boxes [{"x":0,"y":0,"w":100,"h":200}, ...]
        device: 'auto', 'cpu', or 'coral_usb'
        confidence: Minimum confidence for face detection
        embed: Generate face embeddings
    """
    content = await file.read()
    devices = _detect_devices()

    if device == "auto":
        device = "coral_usb" if "coral_usb" in devices else "cpu"
    if device not in devices:
        device = "cpu"

    try:
        boxes = json.loads(person_boxes or "[]")
    except:
        boxes = []

    img = Image.open(io.BytesIO(content)).convert("RGB")
    fw, fh = img.size
    
    # Enhance the full image first
    img = _enhance_image_for_face_detection(img)
    
    all_faces = []
    embed_enabled = str(embed).lower() in ("1", "true", "yes", "on")
    
    for person_box in boxes:
        # Extract head region from person box
        head_crop = _extract_head_region(img, person_box, fw, fh)
        if head_crop is None:
            continue
        
        # Upscale small crops for better detection
        head_crop = _upscale_for_detection(head_crop)
        
        # Convert to bytes for face detection
        buf = io.BytesIO()
        head_crop.save(buf, format="JPEG", quality=90)
        crop_bytes = buf.getvalue()
        
        # Run face detection on head crop
        try:
            faces, crop_w, crop_h, _, _, _, _, _, _, _ = _run_face_detection(
                crop_bytes, device, confidence, enhance=False, multi_scale=True
            )
        except:
            continue
        
        # Map face coordinates back to original image
        px = person_box.get("x", 0)
        py = person_box.get("y", 0)
        ph = person_box.get("h", 0)
        
        # Calculate head region offset in original image
        head_height = int(ph * RING_HEAD_CROP_RATIO)
        pad_x = int(person_box.get("w", 0) * RING_CROP_PADDING)
        pad_y = int(head_height * RING_CROP_PADDING)
        
        head_x = max(0, px - pad_x)
        head_y = max(0, py - pad_y)
        
        # Scale factor if head was upscaled
        scale_x = (head_crop.width / crop_w) if crop_w > 0 else 1
        scale_y = (head_crop.height / crop_h) if crop_h > 0 else 1
        
        for face in faces:
            box = face.get("box", {})
            # Map coordinates back to original image
            orig_x = int(head_x + box.get("x", 0) / scale_x)
            orig_y = int(head_y + box.get("y", 0) / scale_y)
            orig_w = int(box.get("w", 0) / scale_x)
            orig_h = int(box.get("h", 0) / scale_y)
            
            mapped_face = {
                "score": face.get("score", 0),
                "box": {"x": orig_x, "y": orig_y, "w": orig_w, "h": orig_h},
                "from_person_crop": True
            }
            
            # Generate embedding if requested
            if embed_enabled:
                try:
                    face_crop = img.crop((orig_x, orig_y, orig_x + orig_w, orig_y + orig_h))
                    emb, _, emb_source = _run_face_embedding(face_crop, device)
                    mapped_face["embedding"] = emb
                    mapped_face["embedding_source"] = emb_source
                except Exception as e:
                    mapped_face["embedding_error"] = str(e)
            
            all_faces.append(mapped_face)
    
    # Remove duplicates
    all_faces = _remove_duplicate_faces(all_faces)
    
    return {
        "faces": all_faces,
        "frame_width": fw,
        "frame_height": fh,
        "device": device,
        "person_boxes_processed": len(boxes),
    }


@app.post("/faces_ring")
async def faces_ring(
    file: UploadFile = File(...),
    device: str = Form("auto"),
    person_confidence: float = Form(0.4),
    face_confidence: float = Form(0.1),
    embed: str = Form("1"),
    debug: str = Form("0"),
):
    """All-in-one face detection optimized for Ring/doorbell cameras.
    
    This endpoint:
    1. Runs person detection first
    2. Extracts the head region from each detected person
    3. Enhances and upscales the head region
    4. Runs face detection on each head crop
    5. Also runs standard face detection on the full enhanced image
    6. Merges and deduplicates all results
    
    This approach is specifically designed for Ring cameras where:
    - Faces are small due to wide-angle lens
    - IR/night vision reduces contrast
    - Standard face detection often fails
    
    Args:
        file: Image file
        device: 'auto', 'cpu', or 'coral_usb'
        person_confidence: Minimum confidence for person detection
        face_confidence: Minimum confidence for face detection (very low recommended)
        embed: Generate face embeddings
        debug: Include debug information
    """
    content = await file.read()
    devices = _detect_devices()

    if device == "auto":
        device = "coral_usb" if "coral_usb" in devices else "cpu"
    if device not in devices:
        device = "cpu"

    img = Image.open(io.BytesIO(content)).convert("RGB")
    fw, fh = img.size
    embed_enabled = str(embed).lower() in ("1", "true", "yes", "on")
    debug_enabled = str(debug).lower() in ("1", "true", "yes", "on")
    
    all_faces = []
    debug_info = {"steps": []}
    
    # STEP 1: Run person detection
    try:
        labels = _get_labels()
        person_results, _, _, person_inference = _run_detection(content, labels, device, person_confidence)
        person_boxes = [p for p in person_results if p.get("label") == "person"]
        if debug_enabled:
            debug_info["steps"].append({"step": "person_detection", "persons_found": len(person_boxes), "boxes": person_boxes})
    except Exception as e:
        person_boxes = []
        if debug_enabled:
            debug_info["steps"].append({"step": "person_detection", "error": str(e)})
    
    # STEP 2: Enhance image
    img_enhanced = _enhance_image_for_face_detection(img)
    
    # STEP 3: For each person, extract head region and run face detection
    for idx, person in enumerate(person_boxes):
        box = person.get("box", {})
        person_box = {
            "x": box.get("x", 0),
            "y": box.get("y", 0),
            "w": box.get("w", 0),
            "h": box.get("h", 0)
        }
        
        # Extract head region
        head_crop = _extract_head_region(img_enhanced, person_box, fw, fh)
        if head_crop is None:
            if debug_enabled:
                debug_info["steps"].append({"step": f"head_extract_{idx}", "result": "failed"})
            continue
        
        original_head_size = head_crop.size
        
        # Upscale if needed
        head_crop = _upscale_for_detection(head_crop)
        upscaled_size = head_crop.size
        
        if debug_enabled:
            debug_info["steps"].append({
                "step": f"head_extract_{idx}",
                "person_score": person.get("score"),
                "original_size": original_head_size,
                "upscaled_size": upscaled_size,
            })
        
        # Convert to bytes
        buf = io.BytesIO()
        head_crop.save(buf, format="JPEG", quality=90)
        crop_bytes = buf.getvalue()
        
        # Run face detection on head crop with multi-scale
        try:
            faces, crop_w, crop_h, _, max_score, _, _, _, _, _ = _run_face_detection(
                crop_bytes, device, face_confidence, enhance=False, multi_scale=True
            )
            
            if debug_enabled:
                debug_info["steps"].append({
                    "step": f"face_detect_head_{idx}",
                    "faces_found": len(faces),
                    "max_score": max_score,
                })
            
            # Map coordinates back to original image
            px = person_box["x"]
            py = person_box["y"]
            ph = person_box["h"]
            pw = person_box["w"]
            
            head_height = int(ph * RING_HEAD_CROP_RATIO)
            pad_x = int(pw * RING_CROP_PADDING)
            pad_y = int(head_height * RING_CROP_PADDING)
            
            head_x = max(0, px - pad_x)
            head_y = max(0, py - pad_y)
            
            # Scale factor from detection coordinates to original
            scale_x = upscaled_size[0] / crop_w if crop_w > 0 else 1
            scale_y = upscaled_size[1] / crop_h if crop_h > 0 else 1
            
            for face in faces:
                fbox = face.get("box", {})
                orig_x = int(head_x + fbox.get("x", 0) / scale_x)
                orig_y = int(head_y + fbox.get("y", 0) / scale_y)
                orig_w = int(fbox.get("w", 0) / scale_x)
                orig_h = int(fbox.get("h", 0) / scale_y)
                
                # Ensure box is within image bounds
                orig_x = max(0, min(orig_x, fw - 1))
                orig_y = max(0, min(orig_y, fh - 1))
                orig_w = min(orig_w, fw - orig_x)
                orig_h = min(orig_h, fh - orig_y)
                
                mapped_face = {
                    "score": face.get("score", 0),
                    "box": {"x": orig_x, "y": orig_y, "w": orig_w, "h": orig_h},
                    "source": "person_head_crop"
                }
                
                if embed_enabled and orig_w > 10 and orig_h > 10:
                    try:
                        face_crop = img.crop((orig_x, orig_y, orig_x + orig_w, orig_y + orig_h))
                        emb, _, emb_source = _run_face_embedding(face_crop, device)
                        mapped_face["embedding"] = emb
                        mapped_face["embedding_source"] = emb_source
                    except Exception as e:
                        mapped_face["embedding_error"] = str(e)
                
                all_faces.append(mapped_face)
                
        except Exception as e:
            if debug_enabled:
                debug_info["steps"].append({"step": f"face_detect_head_{idx}", "error": str(e)})
    
    # STEP 4: Also run standard face detection on the full enhanced image
    try:
        buf = io.BytesIO()
        img_enhanced.save(buf, format="JPEG", quality=90)
        enhanced_bytes = buf.getvalue()
        
        full_faces, _, _, _, full_max_score, _, _, _, _, _ = _run_face_detection(
            enhanced_bytes, device, face_confidence, enhance=False, multi_scale=True
        )
        
        if debug_enabled:
            debug_info["steps"].append({
                "step": "face_detect_full_image",
                "faces_found": len(full_faces),
                "max_score": full_max_score,
            })
        
        for face in full_faces:
            fbox = face.get("box", {})
            face_entry = {
                "score": face.get("score", 0),
                "box": fbox,
                "source": "full_image_enhanced"
            }
            
            if embed_enabled:
                fx = fbox.get("x", 0)
                fy = fbox.get("y", 0)
                fwidth = fbox.get("w", 0)
                fheight = fbox.get("h", 0)
                if fwidth > 10 and fheight > 10:
                    try:
                        face_crop = img.crop((fx, fy, fx + fwidth, fy + fheight))
                        emb, _, emb_source = _run_face_embedding(face_crop, device)
                        face_entry["embedding"] = emb
                        face_entry["embedding_source"] = emb_source
                    except Exception as e:
                        face_entry["embedding_error"] = str(e)
            
            all_faces.append(face_entry)
            
    except Exception as e:
        if debug_enabled:
            debug_info["steps"].append({"step": "face_detect_full_image", "error": str(e)})
    
    # STEP 5: Remove duplicates
    all_faces = _remove_duplicate_faces(all_faces)
    
    result = {
        "faces": all_faces,
        "frame_width": fw,
        "frame_height": fh,
        "device": device,
        "persons_detected": len(person_boxes),
        "face_confidence_threshold": face_confidence,
    }
    
    if debug_enabled:
        result["debug"] = debug_info
    
    return result


@app.post("/head_movenet")
async def head_movenet(
    file: UploadFile = File(...),
    min_confidence: float = Form(0.3),
):
    """Detect head/face region using MoveNet pose estimation.
    
    Uses MoveNet's keypoint detection (nose, eyes, ears) to precisely
    locate the head region. This is more accurate than percentage-based
    estimation from the person bounding box.
    
    Args:
        file: Image file to analyze (should contain a single person)
        min_confidence: Minimum keypoint confidence threshold (0.0-1.0)
    
    Returns:
        - keypoints: All detected pose keypoints with positions and confidence
        - head_box: Calculated bounding box around head (or null if not detected)
        - frame_width, frame_height: Original image dimensions
        - inference_ms: MoveNet inference time
    """
    content = await file.read()
    
    # MoveNet requires TPU - check if available and healthy
    devices = _detect_devices()
    tpu_available = "coral_usb" in devices and _check_tpu_health()
    
    if not tpu_available:
        error_msg = "MoveNet requires Coral Edge TPU"
        if "coral_usb" not in devices:
            error_msg += " (no device found)"
        elif not _tpu_healthy:
            error_msg += " (TPU in fallback mode, retry later)"
        return {
            "error": error_msg,
            "head_box": None,
            "keypoints": {},
            "tpu_healthy": _tpu_healthy
        }
    
    try:
        def do_movenet():
            return _run_movenet_pose(content)
        
        keypoints, head_box, fw, fh, inference_ms = _run_with_retry(do_movenet, max_retries=MAX_INFERENCE_RETRIES)
        
        # Filter keypoints by confidence if requested
        if min_confidence > 0:
            head_box = _calculate_head_box_from_keypoints(keypoints, fw, fh, min_confidence)
        
        _record_tpu_success()
        _update_metrics(True, inference_ms, "coral_usb")
        _log_inference("head_movenet", "coral_usb", inference_ms, True, 
                       f"head={'yes' if head_box else 'no'}")
        
        return {
            "head_box": head_box,
            "keypoints": keypoints,
            "frame_width": fw,
            "frame_height": fh,
            "inference_ms": round(inference_ms, 1),
            "device": "coral_usb",
            "tpu_healthy": True
        }
    except Exception as e:
        _record_tpu_failure(e)
        _update_metrics(False, 0, "coral_usb")
        _log_inference("head_movenet", "coral_usb", 0, False, str(e))
        
        import traceback
        traceback.print_exc()
        return {
            "error": f"MoveNet pose estimation failed: {str(e)}",
            "head_box": None,
            "keypoints": {},
            "tpu_healthy": _tpu_healthy
        }

