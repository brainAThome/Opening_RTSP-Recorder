"""Tests for the data-mutation logic behind the new per-camera WS commands.

The WS handlers (ws_get_camera_settings / ws_set_camera_setting / ws_delete_camera)
are thin closures over Home Assistant's ConfigEntry; their actual data logic lives
in camera_settings. These tests pin that logic end-to-end the way the handlers use
it: build new_data/new_options dicts, mutate, and verify the merged result.

Run: PYTHONPATH=custom_components/rtsp_recorder pytest tests/test_camera_settings_ws_logic.py
"""
import importlib

cs = importlib.import_module("camera_settings")


def _merged(data, options):
    return {**data, **(options or {})}


class TestSetCameraSettingFlow:
    """Mirrors ws_set_camera_setting: mutate both dicts, then resolve."""

    def test_set_threshold_writes_both_dicts_and_resolves(self):
        data = {"analysis_detector_confidence": 0.4}
        options = {"analysis_detector_confidence": 0.4}
        cs.set_override(data, "analysis_detector_confidence", "Garten vorne", 0.2)
        cs.set_override(options, "analysis_detector_confidence", "Garten vorne", 0.2)
        assert data["detector_confidence_Garten_vorne"] == 0.2
        assert options["detector_confidence_Garten_vorne"] == 0.2
        assert cs.resolve(_merged(data, options),
                          "analysis_detector_confidence", "Garten vorne") == 0.2

    def test_set_to_global_clears_override(self):
        data = {"detector_confidence_Wohnzimmer": 0.2,
                "analysis_detector_confidence": 0.4}
        options = {"detector_confidence_Wohnzimmer": 0.2,
                   "analysis_detector_confidence": 0.4}
        cs.set_override(data, "analysis_detector_confidence", "Wohnzimmer", 0)
        cs.set_override(options, "analysis_detector_confidence", "Wohnzimmer", 0)
        assert "detector_confidence_Wohnzimmer" not in data
        assert "detector_confidence_Wohnzimmer" not in options
        assert cs.resolve(_merged(data, options),
                          "analysis_detector_confidence", "Wohnzimmer") == 0.4

    def test_set_new_bool_field(self):
        data, options = {}, {}
        cs.set_override(data, "analysis_face_enabled", "Garten vorne", False)
        cs.set_override(options, "analysis_face_enabled", "Garten vorne", False)
        assert cs.resolve(_merged(data, options),
                          "analysis_face_enabled", "Garten vorne") is False

    def test_unknown_field_is_rejected_by_get_field(self):
        # ws_set_camera_setting guards with get_field(field) is None
        assert cs.get_field("analysis_device") is None
        assert cs.get_field("analysis_detector_confidence") is not None


class TestGetCameraSettingsFlow:
    """Mirrors ws_get_camera_settings overrides_by_camera construction."""

    def test_overrides_by_camera_map(self):
        cfg = {
            "analysis_detector_confidence": 0.15,
            "detector_confidence_Garten_vorne": 0.1,
            "detector_confidence_Wohnzimmer": 0.25,
            "frame_interval_Garten_vorne": 5,
            "analysis_objects": ["person"],
        }
        overrides_map = {}
        for key in cfg:
            for f in cs.PER_CAMERA_FIELDS:
                if key.startswith(f.prefix):
                    cam = key[len(f.prefix):]
                    overrides_map.setdefault(cam, {})[f.global_key] = cfg.get(key)
        assert overrides_map["Garten_vorne"] == {
            "analysis_detector_confidence": 0.1,
            "analysis_frame_interval": 5,
        }
        assert overrides_map["Wohnzimmer"] == {"analysis_detector_confidence": 0.25}

    def test_prefix_collision_safety(self):
        # face_confidence_ and face_match_threshold_ and face_enabled_/face_multiscale_
        # all start with "face_" - ensure each maps to exactly one field.
        cfg = {
            "face_confidence_Cam": 0.3,
            "face_match_threshold_Cam": 0.6,
            "face_enabled_Cam": True,
            "face_multiscale_Cam": False,
        }
        result = {}
        for key in cfg:
            matched = [f for f in cs.PER_CAMERA_FIELDS if key.startswith(f.prefix)]
            # longest-prefix wins to avoid face_ collisions
            matched.sort(key=lambda f: len(f.prefix), reverse=True)
            if matched:
                f = matched[0]
                result[f.global_key] = key
        assert result["analysis_face_confidence"] == "face_confidence_Cam"
        assert result["analysis_face_match_threshold"] == "face_match_threshold_Cam"
        assert result["analysis_face_enabled"] == "face_enabled_Cam"
        assert result["analysis_face_multiscale"] == "face_multiscale_Cam"


class TestDeleteCameraFlow:
    """Mirrors ws_delete_camera."""

    def test_delete_removes_all_and_keeps_recordings_scope(self):
        data = {
            "sensors_Garten_vorne": ["binary_sensor.x"],
            "duration_Garten_vorne": 90,
            "rtsp_url_Garten_vorne": "rtsp://example",
            "detector_confidence_Garten_vorne": 0.1,
            "frame_interval_Garten_vorne": 5,
            "analysis_detector_confidence": 0.4,
            "sensors_Wohnzimmer": ["binary_sensor.y"],
        }
        options = {"detector_confidence_Garten_vorne": 0.1}
        removed = cs.delete_camera(data, options, "Garten vorne")
        assert "sensors_Garten_vorne" in removed
        assert "detector_confidence_Garten_vorne" in removed
        # other camera + globals survive
        assert "sensors_Wohnzimmer" in data
        assert "analysis_detector_confidence" in data
        # both dicts cleaned
        assert not any(k.endswith("_Garten_vorne") for k in data)
        assert not any(k.endswith("_Garten_vorne") for k in options)

    def test_delete_nonexistent_returns_empty(self):
        assert cs.delete_camera({}, {}, "Ghost") == []
