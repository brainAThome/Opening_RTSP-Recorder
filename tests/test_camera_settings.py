"""Unit tests for the central per-camera settings module.

These tests pin the behaviour that the rest of the refactor depends on:
- key normalisation is identical to the legacy sanitize_camera_key,
- per-camera override resolves with fallback to global then default,
- legacy "0 = use global" sentinel is preserved for the 4 old fields,
- new fields use explicit presence (absent = global),
- deletion removes every per-camera key from both data and options.

Run: PYTHONPATH=custom_components/rtsp_recorder pytest tests/test_camera_settings.py
"""
import importlib

import pytest

cs = importlib.import_module("camera_settings")


def _legacy_sanitize(name: str) -> str:
    """Reference copy of config_flow.sanitize_camera_key.

    config_flow.py cannot be imported standalone in the test environment (it does
    a relative ``from .analysis import ...``), so we pin the exact algorithm here.
    If config_flow.sanitize_camera_key ever changes, this copy and the test must
    be updated together - that is the point of the equivalence test.
    """
    import re
    clean = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")
    for char in [":", "/", "\\", "?", "*", '"', "<", ">", "|"]:
        clean = clean.replace(char, "")
    return clean or "unknown"


class TestCameraKey:
    def test_matches_legacy_sanitize(self):
        for name in [
            "Garten vorne", "Wohnzimmer", "Flur oben", "Haustuer",
            "Thorins Zimmer", "Test-Cam", "Cam: Eingang/Tor", "Hof (Nord)",
            "  spaced  ", "a/b\\c?d*e", "Garten_vorne",
        ]:
            assert cs.camera_key(name) == _legacy_sanitize(name), name

    def test_spaces_to_underscore(self):
        assert cs.camera_key("Garten vorne") == "Garten_vorne"

    def test_empty(self):
        # Mirrors legacy sanitize_camera_key: empty input -> "unknown"
        assert cs.camera_key("") == "unknown"
        assert cs.camera_key(None) == "unknown"


class TestResolveLegacyThreshold:
    def test_per_cam_wins(self):
        cfg = {"analysis_detector_confidence": 0.4,
               "detector_confidence_Garten_vorne": 0.1}
        assert cs.resolve(cfg, "analysis_detector_confidence", "Garten vorne") == 0.1

    def test_falls_back_to_global(self):
        cfg = {"analysis_detector_confidence": 0.4}
        assert cs.resolve(cfg, "analysis_detector_confidence", "Wohnzimmer") == 0.4

    def test_zero_per_cam_means_global(self):
        # legacy sentinel: stored 0 -> use global
        cfg = {"analysis_detector_confidence": 0.4,
               "detector_confidence_Wohnzimmer": 0}
        assert cs.resolve(cfg, "analysis_detector_confidence", "Wohnzimmer") == 0.4

    def test_falls_back_to_default_when_nothing_set(self):
        assert cs.resolve({}, "analysis_detector_confidence", "X") == cs.DEFAULT_DETECTOR_CONFIDENCE


class TestResolveObjects:
    def test_per_cam_list_wins(self):
        cfg = {"analysis_objects": ["person"],
               "analysis_objects_Garten_vorne": ["car", "person"]}
        assert cs.resolve(cfg, "analysis_objects", "Garten vorne") == ["car", "person"]

    def test_empty_list_falls_back_to_global(self):
        cfg = {"analysis_objects": ["person"], "analysis_objects_X": []}
        assert cs.resolve(cfg, "analysis_objects", "X") == ["person"]


class TestResolveNewFields:
    def test_frame_interval_per_cam(self):
        cfg = {"analysis_frame_interval": 2, "frame_interval_Garten_vorne": 5}
        assert cs.resolve(cfg, "analysis_frame_interval", "Garten vorne") == 5

    def test_new_bool_false_is_not_global(self):
        # new fields use explicit presence; False is a real stored value, not "global"
        cfg = {"analysis_face_enabled": True, "face_enabled_Wohnzimmer": False}
        assert cs.resolve(cfg, "analysis_face_enabled", "Wohnzimmer") is False

    def test_new_field_absent_uses_global(self):
        cfg = {"analysis_face_enabled": True}
        assert cs.resolve(cfg, "analysis_face_enabled", "Wohnzimmer") is True


class TestSetClearOverride:
    def test_set_writes_key(self):
        d = {}
        cs.set_override(d, "analysis_detector_confidence", "Garten vorne", 0.2)
        assert d["detector_confidence_Garten_vorne"] == 0.2

    def test_set_zero_legacy_removes_key(self):
        d = {"detector_confidence_Garten_vorne": 0.2}
        cs.set_override(d, "analysis_detector_confidence", "Garten vorne", 0)
        assert "detector_confidence_Garten_vorne" not in d

    def test_set_new_bool_false_is_stored(self):
        d = {}
        cs.set_override(d, "analysis_face_enabled", "Wohnzimmer", False)
        assert d["face_enabled_Wohnzimmer"] is False

    def test_clear_removes(self):
        d = {"detector_confidence_X": 0.2}
        cs.clear_override(d, "analysis_detector_confidence", "X")
        assert "detector_confidence_X" not in d

    def test_unknown_field_raises(self):
        with pytest.raises(KeyError):
            cs.set_override({}, "analysis_device", "X", "cpu")


class TestCameraOverrides:
    def test_lists_only_overridden(self):
        cfg = {
            "analysis_detector_confidence": 0.4,
            "detector_confidence_Garten_vorne": 0.1,
            "frame_interval_Garten_vorne": 5,
        }
        ov = cs.camera_overrides(cfg, "Garten vorne")
        assert ov == {"analysis_detector_confidence": 0.1, "analysis_frame_interval": 5}


class TestDeletion:
    def _full_camera_cfg(self):
        return {
            "sensors_Garten_vorne": ["binary_sensor.x"],
            "duration_Garten_vorne": 90,
            "snapshot_delay_Garten_vorne": 3,
            "rtsp_url_Garten_vorne": "rtsp://x",
            "retention_hours_Garten_vorne": 24,
            "analysis_objects_Garten_vorne": ["car"],
            "detector_confidence_Garten_vorne": 0.1,
            "face_confidence_Garten_vorne": 0.2,
            "face_match_threshold_Garten_vorne": 0.5,
            "frame_interval_Garten_vorne": 5,
            # unrelated keys must survive:
            "analysis_detector_confidence": 0.4,
            "sensors_Wohnzimmer": ["binary_sensor.y"],
        }

    def test_collect_keys(self):
        keys = cs.collect_camera_keys(self._full_camera_cfg().keys(), "Garten vorne")
        assert "analysis_detector_confidence" not in keys
        assert "sensors_Wohnzimmer" not in keys
        assert "sensors_Garten_vorne" in keys
        assert "frame_interval_Garten_vorne" in keys

    def test_delete_camera_cleans_both_dicts(self):
        data = {"sensors_Garten_vorne": ["a"], "duration_Garten_vorne": 90}
        options = {"detector_confidence_Garten_vorne": 0.1,
                   "analysis_detector_confidence": 0.4}
        removed = cs.delete_camera(data, options, "Garten vorne")
        assert "sensors_Garten_vorne" in removed
        assert "detector_confidence_Garten_vorne" in removed
        assert data == {}
        assert options == {"analysis_detector_confidence": 0.4}  # global survives

    def test_delete_preserves_other_cameras(self):
        cfg = self._full_camera_cfg()
        cs.delete_camera(cfg, {}, "Garten vorne")
        assert "sensors_Wohnzimmer" in cfg
        assert "analysis_detector_confidence" in cfg
        assert not any(k.endswith("_Garten_vorne") for k in cfg)
