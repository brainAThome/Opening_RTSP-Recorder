import os
import json
import urllib.request
import io
import time
import threading
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

# Face Embedding (EdgeTPU kompatibel, Beispielmodell)
FACE_EMBED_CPU_URL = "https://github.com/google-coral/test_data/raw/release-frogfish/mobilefacenet.tflite"
FACE_EMBED_CORAL_URL = "https://github.com/google-coral/test_data/raw/release-frogfish/mobilefacenet_edgetpu.tflite"

# BodyPix - Body Part Segmentation (includes face detection via segmentation)
# Using models WITHOUT decoder (no custom op required)
BODYPIX_CPU_URL = "https://github.com/google-coral/project-bodypix/raw/master/models/bodypix_mobilenet_v1_075_720_1280_16_quant.tflite"
BODYPIX_CORAL_URL = "https://github.com/google-coral/project-bodypix/raw/master/models/bodypix_mobilenet_v1_075_720_1280_16_quant_edgetpu.tflite"

# BodyPix body part labels (indices 0 and 1 are face parts)
BODYPIX_PARTS = {
    0: "left_face", 1: "right_face",
    2: "left_upper_arm_front", 3: "left_upper_arm_back",
    4: "right_upper_arm_front", 5: "right_upper_arm_back",
    6: "left_lower_arm_front", 7: "left_lower_arm_back",
    8: "right_lower_arm_front", 9: "right_lower_arm_back",
    10: "left_hand", 11: "right_hand",
    12: "torso_front", 13: "torso_back",
    14: "left_upper_leg_front", 15: "left_upper_leg_back",
    16: "right_upper_leg_front", 17: "right_upper_leg_back",
    18: "left_lower_leg_front", 19: "left_lower_leg_back",
    20: "right_lower_leg_front", 21: "right_lower_leg_back",
    22: "left_foot", 23: "right_foot"
}
BODYPIX_FACE_PARTS = {0, 1}  # left_face and right_face

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
_cached_bodypix: Dict[str, Any] = {}
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


def _get_bodypix_model(device: str) -> str:
    """Download or return cached BodyPix model path."""
    if device == "coral_usb":
        url = BODYPIX_CORAL_URL
        filename = "bodypix_no_decoder_edgetpu.tflite"
    else:
        url = BODYPIX_CPU_URL
        filename = "bodypix_no_decoder.tflite"
    
    model_path = os.path.join(MODEL_DIR, filename)
    if not os.path.exists(model_path):
        print(f"Downloading BodyPix model: {filename}")
        os.makedirs(MODEL_DIR, exist_ok=True)
        urllib.request.urlretrieve(url, model_path)
    return model_path


def _get_cached_bodypix_interpreter(device: str):
    """Get or create cached BodyPix interpreter."""
    global _cached_bodypix
    with _interpreter_lock:
        if device in _cached_bodypix:
            try:
                _cached_bodypix[device].get_input_details()
                return _cached_bodypix[device]
            except Exception as e:
                print(f"Cached BodyPix interpreter for {device} invalid, recreating: {e}")
                del _cached_bodypix[device]
        
        try:
            model_path = _get_bodypix_model(device)
            interpreter = _build_interpreter(model_path, device)
            interpreter.allocate_tensors()
            _cached_bodypix[device] = interpreter
            print(f"Created and cached BodyPix for device: {device}")
            return interpreter
        except Exception as e:
            print(f"ERROR creating BodyPix interpreter for {device}: {e}")
            if device in _cached_bodypix:
                del _cached_bodypix[device]
            raise


def _run_bodypix_segmentation(img_bytes: bytes, device: str):
    """Run BodyPix segmentation on image.
    
    BodyPix model without decoder outputs:
    - float_heatmaps [1, H, W, 17] - Pose keypoint heatmaps
    - float_short_offsets [1, H, W, 34]
    - float_mid_offsets [1, H, W, 64]
    - float_segments [1, H, W, 1] - Person segmentation mask
    - float_part_heatmaps [1, H, W, 24] - Body part heatmaps (24 parts)
    - float_long_offsets [1, H, W, 34]
    
    Returns:
        - part_segmentation: numpy array with body part indices (argmax of part_heatmaps)
        - person_mask: boolean array where True = person pixel
        - frame_width, frame_height: original image dimensions
        - model_width, model_height: model output dimensions
        - inference_ms: inference time in milliseconds
    """
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    frame_width, frame_height = img.size
    
    interpreter = _get_cached_bodypix_interpreter(device)
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    
    # Model expects 1280x720 input (or similar based on model variant)
    input_shape = input_details[0]["shape"]
    target_h, target_w = int(input_shape[1]), int(input_shape[2])
    img_resized = img.resize((target_w, target_h))
    
    # Prepare input tensor
    input_data = np.expand_dims(np.array(img_resized, dtype=np.uint8), axis=0)
    
    interpreter.set_tensor(input_details[0]["index"], input_data)
    
    start = time.perf_counter()
    interpreter.invoke()
    inference_ms = (time.perf_counter() - start) * 1000
    
    # Get outputs by name
    outputs = {}
    for d in output_details:
        name = d.get("name", "")
        tensor = interpreter.get_tensor(d["index"])
        outputs[name] = tensor
    
    # Get person segmentation (float_segments)
    segments = outputs.get("float_segments")
    # Get body part heatmaps (float_part_heatmaps)
    part_heatmaps = outputs.get("float_part_heatmaps")
    
    if segments is None or part_heatmaps is None:
        return None, None, frame_width, frame_height, 0, 0, inference_ms
    
    # Remove batch dimension
    segments = segments[0]  # [H, W, 1]
    part_heatmaps = part_heatmaps[0]  # [H, W, 24]
    
    model_height, model_width = segments.shape[:2]
    
    # Person mask: segments > threshold (values are uint8 0-255, so ~128 is threshold)
    person_mask = segments[:, :, 0] > 128
    
    # Body part segmentation: argmax over 24 body parts
    # Only where person is detected
    part_segmentation = np.argmax(part_heatmaps, axis=-1)  # [H, W]
    
    # Mask out non-person areas
    part_segmentation = np.where(person_mask, part_segmentation, -1)
    
    return part_segmentation, person_mask, frame_width, frame_height, model_width, model_height, inference_ms


def _extract_faces_from_bodypix(segmentation_mask, person_mask, frame_width, frame_height, 
                                  model_width, model_height, min_face_pixels=20):
    """Extract face bounding boxes from BodyPix segmentation mask.
    
    Face parts in BodyPix:
    - 0: left_face
    - 1: right_face
    
    Uses clustering to find actual face regions, not just scattered pixels.
    
    Returns list of face detections with bounding boxes.
    """
    faces = []
    
    # Scale factors from model space to original image space
    scale_x = frame_width / model_width
    scale_y = frame_height / model_height
    
    # Find face pixels (parts 0 and 1)
    face_mask = np.isin(segmentation_mask, list(BODYPIX_FACE_PARTS))
    
    if not face_mask.any():
        return faces
    
    # Find torso pixels (12 = torso_front, 13 = torso_back) for lower boundary
    torso_mask = np.isin(segmentation_mask, [12, 13])
    torso_top_y = None
    if torso_mask.any():
        torso_y_coords, torso_x_coords = np.where(torso_mask)
        torso_top_y = torso_y_coords.min()  # Topmost torso pixel
    
    # Get all face pixel coordinates
    y_coords, x_coords = np.where(face_mask)
    total_pixels = len(y_coords)
    
    if total_pixels < min_face_pixels:
        return faces
    
    # Simple clustering: find the densest region of face pixels
    # Calculate centroid of all face pixels
    center_y = np.mean(y_coords)
    center_x = np.mean(x_coords)
    
    # Calculate distances from centroid
    distances = np.sqrt((y_coords - center_y)**2 + (x_coords - center_x)**2)
    
    # Keep only pixels within 2 standard deviations (removes outliers)
    std_dist = np.std(distances) if len(distances) > 1 else 1
    mean_dist = np.mean(distances)
    threshold = mean_dist + 2 * std_dist
    
    # Filter to core pixels
    core_mask = distances <= threshold
    core_y = y_coords[core_mask]
    core_x = x_coords[core_mask]
    
    if len(core_y) < min_face_pixels:
        return faces
    
    # Calculate bounding box from core face pixels
    face_y_min, face_y_max = core_y.min(), core_y.max()
    x_min, x_max = core_x.min(), core_x.max()
    
    # Use torso top as lower boundary if available (extends face box down to neck/chin)
    if torso_top_y is not None and torso_top_y > face_y_max:
        y_max = torso_top_y
    else:
        y_max = face_y_max
    y_min = face_y_min
    
    # Validate box dimensions in model space
    model_box_w = x_max - x_min + 1
    model_box_h = y_max - y_min + 1
    
    # Reject boxes that are too wide (> 40% of model width) - probably noise
    if model_box_w > model_width * 0.4:
        return faces
    
    # Reject boxes with very low pixel density (use original face area for density calc)
    face_box_area = (x_max - x_min + 1) * (face_y_max - face_y_min + 1)
    pixel_count = len(core_y)
    pixel_density = pixel_count / max(face_box_area, 1)
    
    if pixel_density < 0.15:  # Less than 15% filled = not a face
        return faces
    
    # Scale to original image coordinates
    box_x = int(x_min * scale_x)
    box_y = int(y_min * scale_y)
    box_w = int(model_box_w * scale_x)
    box_h = int(model_box_h * scale_y)
    
    # Expand box slightly to include forehead and sides (less expansion since torso gives us bottom)
    expand_w = int(box_w * 0.3)  # 30% horizontal expansion for ears
    expand_h_top = int(box_h * 0.2)  # 20% top expansion for forehead
    
    box_x = max(0, box_x - expand_w)
    box_y = max(0, box_y - expand_h_top)
    box_w = min(frame_width - box_x, box_w + 2 * expand_w)
    box_h = min(frame_height - box_y, box_h + expand_h_top)  # Only expand top, torso is bottom
    
    # Make box more square (heads are roughly square)
    if box_w > box_h * 1.3:
        diff = box_w - int(box_h * 1.1)
        box_x += diff // 2
        box_w -= diff
    elif box_h > box_w * 1.3:
        diff = box_h - int(box_w * 1.1)
        box_y += diff // 2
        box_h -= diff
    
    # Sanity check: face shouldn't be larger than 45% of frame (increased for expanded box)
    if box_w > frame_width * 0.45 or box_h > frame_height * 0.45:
        return faces
    
    # Score based on pixel count and density
    score = min(0.99, pixel_density * (pixel_count / 50))
    
    faces.append({
        "score": round(score, 3),
        "box": {"x": box_x, "y": box_y, "w": box_w, "h": box_h},
        "face_pixels": int(pixel_count),
        "method": "bodypix"
    })
    
    return faces


def _extract_body_parts_from_bodypix(segmentation_mask, person_mask, frame_width, frame_height,
                                      model_width, model_height):
    """Extract all body part bounding boxes from BodyPix segmentation mask.
    
    Returns list of body part detections.
    """
    body_parts = []
    
    scale_x = frame_width / model_width
    scale_y = frame_height / model_height
    
    for part_id, part_name in BODYPIX_PARTS.items():
        part_mask = segmentation_mask == part_id
        if not part_mask.any():
            continue
        
        y_coords, x_coords = np.where(part_mask)
        if len(y_coords) < 5:  # Minimum pixels
            continue
        
        y_min, y_max = y_coords.min(), y_coords.max()
        x_min, x_max = x_coords.min(), x_coords.max()
        
        box_x = int(x_min * scale_x)
        box_y = int(y_min * scale_y)
        box_w = int((x_max - x_min + 1) * scale_x)
        box_h = int((y_max - y_min + 1) * scale_y)
        
        body_parts.append({
            "part_id": part_id,
            "part_name": part_name,
            "box": {"x": box_x, "y": box_y, "w": box_w, "h": box_h},
            "pixel_count": int(len(y_coords))
        })
    
    return body_parts


def _parse_detection_outputs(output_details, outputs, is_face_model: bool = False):
    boxes = classes = scores = None
    count = 0
    names = [(detail.get("name") or "") for detail in output_details]
    if len(outputs) >= 4 and all("TFLite_Detection_PostProcess" in name for name in names):
        boxes = outputs[0]
        # Face models: output[1] contains scores, output[2] contains classes (all zeros for single class)
        # Object detection models: output[1] contains classes, output[2] contains scores
        if is_face_model:
            # For face detection, scores are in output[1], classes in output[2]
            scores = outputs[1]
            classes = outputs[2]
        else:
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

    if device == "auto":
        device = "coral_usb" if "coral_usb" in devices else "cpu"
    if device not in devices:
        device = "cpu"

    enhance_enabled = str(enhance).lower() in ("1", "true", "yes", "on")
    multi_scale_enabled = str(multi_scale).lower() in ("1", "true", "yes", "on")

    try:
        faces_list, fw, fh, inference_ms, max_score, scores_dtype, output_info, input_info, input_details_raw, input_details_error = _run_face_detection(
            content, device, confidence, enhance=enhance_enabled, multi_scale=multi_scale_enabled
        )
    except RuntimeError as e:
        if device == "coral_usb" and "EdgeTpu" in str(e):
            device = "cpu"
            faces_list, fw, fh, inference_ms, max_score, scores_dtype, output_info, input_info, input_details_raw, input_details_error = _run_face_detection(
                content, device, confidence, enhance=enhance_enabled, multi_scale=multi_scale_enabled
            )
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


@app.post("/faces_bodypix")
async def faces_bodypix(
    file: UploadFile = File(...),
    device: str = Form("auto"),
    min_face_pixels: int = Form(50),
    embed: str = Form("1"),
    include_body_parts: str = Form("0"),
):
    """Detect faces using BodyPix body part segmentation.
    
    This is optimized for Ring/doorbell cameras where traditional face detection fails.
    BodyPix segments the image into 24 body parts, including left_face and right_face.
    
    Advantages over standard face detection:
    - Works with side profiles
    - Works with small faces in wide-angle cameras
    - Works with IR/night vision images
    - Detects faces as part of full body recognition
    
    Args:
        file: Image file to analyze
        device: 'auto', 'cpu', or 'coral_usb'
        min_face_pixels: Minimum number of face pixels to count as detection (default 50)
        embed: Generate face embeddings ('1' or '0')
        include_body_parts: Include all detected body parts in response ('1' or '0')
    """
    content = await file.read()
    devices = _detect_devices()
    
    if device == "auto":
        device = "coral_usb" if "coral_usb" in devices else "cpu"
    if device not in devices:
        device = "cpu"
    
    embed_enabled = str(embed).lower() in ("1", "true", "yes", "on")
    include_parts = str(include_body_parts).lower() in ("1", "true", "yes", "on")
    
    # Run BodyPix segmentation
    try:
        segmentation_mask, person_mask, fw, fh, model_w, model_h, inference_ms = _run_bodypix_segmentation(
            content, device
        )
    except Exception as e:
        return {
            "error": f"BodyPix segmentation failed: {str(e)}",
            "faces": [],
            "device": device,
        }
    
    if segmentation_mask is None:
        return {
            "faces": [],
            "frame_width": fw,
            "frame_height": fh,
            "device": device,
            "inference_ms": round(inference_ms, 1),
            "person_detected": False,
        }
    
    # Check if any person detected
    person_detected = bool(person_mask is not None and person_mask.any())
    person_pixel_count = int(person_mask.sum()) if person_detected else 0

    # Extract faces from segmentation
    faces = _extract_faces_from_bodypix(
        segmentation_mask, person_mask, fw, fh,
        model_w, model_h,
        min_face_pixels=min_face_pixels
    )
    
    # Generate embeddings if requested
    embed_total_ms = 0.0
    if embed_enabled and faces:
        img = Image.open(io.BytesIO(content)).convert("RGB")
        for face in faces:
            box = face.get("box", {})
            x = max(int(box.get("x", 0)), 0)
            y = max(int(box.get("y", 0)), 0)
            w = max(int(box.get("w", 0)), 1)
            h = max(int(box.get("h", 0)), 1)
            x2 = min(x + w, fw)
            y2 = min(y + h, fh)
            
            if w > 10 and h > 10:
                try:
                    crop = img.crop((x, y, x2, y2))
                    emb, emb_ms, emb_source = _run_face_embedding(crop, device)
                    embed_total_ms += emb_ms
                    face["embedding"] = emb
                    face["embedding_source"] = emb_source
                except Exception as e:
                    face["embedding_error"] = str(e)
    
    result = {
        "faces": faces,
        "frame_width": fw,
        "frame_height": fh,
        "device": device,
        "inference_ms": round(inference_ms, 1),
        "embedding_ms": round(embed_total_ms, 1),
        "person_detected": person_detected,
        "person_pixel_count": person_pixel_count,
    }
    
    # Include body parts if requested
    if include_parts:
        body_parts = _extract_body_parts_from_bodypix(
            segmentation_mask, person_mask, fw, fh,
            model_w, model_h
        )
        result["body_parts"] = body_parts
    
    return result


@app.post("/bodypix")
async def bodypix_full(
    file: UploadFile = File(...),
    device: str = Form("auto"),
):
    """Run full BodyPix body part segmentation.
    
    Returns all detected body parts with their bounding boxes.
    Useful for debugging or advanced applications.
    
    Args:
        file: Image file to analyze
        device: 'auto', 'cpu', or 'coral_usb'
    """
    content = await file.read()
    devices = _detect_devices()
    
    if device == "auto":
        device = "coral_usb" if "coral_usb" in devices else "cpu"
    if device not in devices:
        device = "cpu"
    
    try:
        segmentation_mask, person_mask, fw, fh, model_w, model_h, inference_ms = _run_bodypix_segmentation(
            content, device
        )
    except Exception as e:
        return {
            "error": f"BodyPix segmentation failed: {str(e)}",
            "body_parts": [],
            "device": device,
        }
    
    if segmentation_mask is None:
        return {
            "body_parts": [],
            "frame_width": fw,
            "frame_height": fh,
            "device": device,
            "inference_ms": round(inference_ms, 1),
            "person_detected": False,
        }
    
    person_detected = bool(person_mask is not None and person_mask.any())
    person_pixel_count = int(person_mask.sum()) if person_detected else 0

    # Extract all body parts
    body_parts = _extract_body_parts_from_bodypix(
        segmentation_mask, person_mask, fw, fh,
        model_w, model_h
    )
    
    # Also extract faces separately
    faces = _extract_faces_from_bodypix(
        segmentation_mask, person_mask, fw, fh,
        model_w, model_h
    )
    
    return {
        "body_parts": body_parts,
        "faces": faces,
        "frame_width": fw,
        "frame_height": fh,
        "device": device,
        "inference_ms": round(inference_ms, 1),
        "person_detected": person_detected,
        "person_pixel_count": person_pixel_count,
    }
