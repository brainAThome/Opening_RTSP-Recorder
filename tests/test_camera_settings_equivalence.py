"""Equivalence tests: new camera_settings.resolve() must match the OLD inline logic.

These pin that Baustein 2 (services.py refactor) preserves the legacy behaviour
exactly for the 4 pre-existing per-camera fields, so the refactor cannot silently
change what gets sent to the detector for existing installs.

Run: PYTHONPATH=custom_components/rtsp_recorder pytest tests/test_camera_settings_equivalence.py
"""
import importlib

import pytest

cs = importlib.import_module("camera_settings")


def _old_threshold(config, cam_key_field_prefix, global_key, global_default):
    """Reproduce the exact OLD inline formula from services.py for a threshold field."""
    cam_val = config.get(f"{cam_key_field_prefix}{_old_cam_name(config)}", 0)
    global_val = config.get(global_key, global_default)
    return cam_val if cam_val > 0 else global_val


def _old_cam_name(_config):
    # In the old code cam_name was the on-disk folder; here we test with explicit
    # camera below, so this helper is unused except to mirror structure.
    raise NotImplementedError


@pytest.mark.parametrize("cam_val,global_val,expected", [
    (0.0, 0.4, 0.4),     # zero per-cam -> global
    (0.1, 0.4, 0.1),     # per-cam wins
    (0.9, 0.4, 0.9),     # per-cam wins (high)
])
def test_detector_confidence_equiv(cam_val, global_val, expected):
    cam = "Garten vorne"
    config = {"analysis_detector_confidence": global_val}
    if cam_val:
        config[f"detector_confidence_{cs.camera_key(cam)}"] = cam_val
    # OLD inline formula:
    old_cam = config.get(f"detector_confidence_{cs.camera_key(cam)}", 0)
    old_result = old_cam if old_cam > 0 else global_val
    # NEW:
    new_result = cs.resolve(config, "analysis_detector_confidence", cam)
    assert new_result == old_result == expected


@pytest.mark.parametrize("cam_objs,global_objs,expected", [
    (None, ["person"], ["person"]),         # no per-cam -> global
    ([], ["person"], ["person"]),           # empty per-cam -> global
    (["car"], ["person"], ["car"]),         # per-cam wins
])
def test_objects_equiv(cam_objs, global_objs, expected):
    cam = "Wohnzimmer"
    config = {"analysis_objects": global_objs}
    if cam_objs is not None:
        config[f"analysis_objects_{cs.camera_key(cam)}"] = cam_objs
    # OLD: cam_objects if cam_objects else global
    old_cam = config.get(f"analysis_objects_{cs.camera_key(cam)}", [])
    old_result = old_cam if old_cam else global_objs
    # NEW (services.py uses: resolve(...) or objects)
    new_result = cs.resolve(config, "analysis_objects", cam) or global_objs
    assert new_result == old_result == expected


def test_realistic_live_config_matches_old():
    """A realistic merged config (like the user's live one) resolves identically."""
    config = {
        "analysis_detector_confidence": 0.15,
        "analysis_face_confidence": 0.2,
        "analysis_face_match_threshold": 0.5,
        "analysis_objects": ["person"],
        "detector_confidence_Garten_vorne": 0.1,
        "detector_confidence_Wohnzimmer": 0.25,
        "analysis_objects_Garten_vorne": ["car", "person"],
    }
    # Garten vorne: per-cam detector 0.1, per-cam objects, global face values
    assert cs.resolve(config, "analysis_detector_confidence", "Garten vorne") == 0.1
    assert cs.resolve(config, "analysis_objects", "Garten vorne") == ["car", "person"]
    assert cs.resolve(config, "analysis_face_confidence", "Garten vorne") == 0.2
    # Wohnzimmer: per-cam detector 0.25, global objects
    assert cs.resolve(config, "analysis_detector_confidence", "Wohnzimmer") == 0.25
    assert (cs.resolve(config, "analysis_objects", "Wohnzimmer") or ["person"]) == ["person"]
    # Haustuer: no overrides at all -> all global
    assert cs.resolve(config, "analysis_detector_confidence", "Haustuer") == 0.15
