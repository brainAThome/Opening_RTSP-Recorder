"""Guard test: config_flow per-camera key prefixes must match camera_settings.

The per-camera config keys are written in config_flow.py and read in services.py
via camera_settings. If a prefix drifts between the two (e.g. a typo), overrides
break silently and fall back to global. This test pins that every per-camera field
camera_settings knows about has a matching ``f"{prefix}{safe_name}"`` key definition
in config_flow.py, so the two stay in sync.

Run: PYTHONPATH=custom_components/rtsp_recorder pytest tests/test_config_flow_keys.py
"""
import importlib
import pathlib

cs = importlib.import_module("camera_settings")

_CONFIG_FLOW = pathlib.Path(__file__).resolve().parents[1] / \
    "custom_components" / "rtsp_recorder" / "config_flow.py"


def test_config_flow_defines_all_per_camera_keys():
    src = _CONFIG_FLOW.read_text(encoding="utf-8")
    missing = []
    for f in cs.PER_CAMERA_FIELDS:
        # config_flow builds keys as f"{prefix}{safe_name}"
        needle = f'f"{f.prefix}{{safe_name}}"'
        if needle not in src:
            missing.append((f.global_key, needle))
    assert not missing, f"config_flow.py missing per-camera key defs: {missing}"


def test_config_flow_has_new_form_fields():
    src = _CONFIG_FLOW.read_text(encoding="utf-8")
    for field in (
        "camera_frame_interval",
        "camera_face_enabled",
        "camera_face_multiscale",
        "camera_overlay_smoothing",
    ):
        assert f'"{field}"' in src, f"form field {field} missing from config_flow.py"


def test_tristate_write_logic_matches_camera_settings():
    """Replicate config_flow's tri-state + frame_interval write logic and verify
    the resulting dict resolves correctly through camera_settings."""
    safe = cs.camera_key("Garten vorne")
    cache = {}

    # frame_interval: 0 = global (not stored), >0 stored
    def write_frame_interval(value):
        key = f"frame_interval_{safe}"
        fi = int(value or 0)
        if fi > 0:
            cache[key] = fi
        else:
            cache.pop(key, None)

    # tri-state bool: "global" clears, "on"/"off" store True/False
    def write_tri(prefix, value):
        key = f"{prefix}{safe}"
        if value == "global":
            cache.pop(key, None)
        else:
            cache[key] = (value == "on")

    write_frame_interval(5)
    write_tri("face_enabled_", "off")
    write_tri("face_multiscale_", "on")
    write_tri("overlay_smoothing_", "global")

    cfg = {
        "analysis_frame_interval": 2,
        "analysis_face_enabled": True,
        "analysis_face_multiscale": False,
        "analysis_overlay_smoothing": True,
        **cache,
    }
    assert cs.resolve(cfg, "analysis_frame_interval", "Garten vorne") == 5
    assert cs.resolve(cfg, "analysis_face_enabled", "Garten vorne") is False
    assert cs.resolve(cfg, "analysis_face_multiscale", "Garten vorne") is True
    # overlay was "global" -> not stored -> falls back to global True
    assert cs.resolve(cfg, "analysis_overlay_smoothing", "Garten vorne") is True

    # frame_interval 0 clears the override -> back to global
    write_frame_interval(0)
    cfg2 = {"analysis_frame_interval": 2, **cache}
    assert cs.resolve(cfg2, "analysis_frame_interval", "Garten vorne") == 2
