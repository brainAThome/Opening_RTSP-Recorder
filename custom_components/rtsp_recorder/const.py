"""Constants for RTSP Recorder Integration.

This module contains all constants used across the integration.
It has NO dependencies on other integration modules to prevent circular imports.
"""
import re
import sys

# ===== Domain =====
DOMAIN = "rtsp_recorder"

# ===== Platform Detection (MED-001 Fix) =====
IS_LINUX = sys.platform.startswith('linux')

# ===== People Database =====
PEOPLE_DB_VERSION = 1
PEOPLE_DB_DEFAULT_PATH = "/config/rtsp_recorder_people.json"

# ===== SQLite Database (v1.0.9+) =====
SQLITE_DB_DEFAULT_PATH = "/config/rtsp_recorder/rtsp_recorder.db"
CONF_USE_SQLITE = "use_sqlite"
DEFAULT_USE_SQLITE = True

# ===== Rate Limiting (MED-004 Fix) =====
MAX_CONCURRENT_ANALYSES = 2

# ===== Input Validation (MED-002 Fix) =====
MAX_PERSON_NAME_LENGTH = 100
# Allow letters, numbers, spaces, hyphens, dots, apostrophes, German umlauts
VALID_NAME_PATTERN = re.compile(r"^[\w\s\-\.'\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df]+$")

# ===== Analysis Defaults =====
DEFAULT_STORAGE_PATH = "/media/rtsp_recordings"
DEFAULT_SNAPSHOT_PATH = "/config/www/thumbnails"
DEFAULT_RETENTION_DAYS = 7
DEFAULT_SNAPSHOT_RETENTION_DAYS = 7
DEFAULT_ANALYSIS_FRAME_INTERVAL = 2
DEFAULT_DETECTOR_CONFIDENCE = 0.4
DEFAULT_FACE_CONFIDENCE = 0.2
DEFAULT_FACE_MATCH_THRESHOLD = 0.35

# ===== WebSocket API Types =====
WS_TYPE_GET_ANALYSIS_OVERVIEW = f"{DOMAIN}/get_analysis_overview"
WS_TYPE_GET_ANALYSIS_RESULT = f"{DOMAIN}/get_analysis_result"
WS_TYPE_GET_DETECTOR_STATS = f"{DOMAIN}/get_detector_stats"
WS_TYPE_TEST_INFERENCE = f"{DOMAIN}/test_inference"
WS_TYPE_GET_ANALYSIS_CONFIG = f"{DOMAIN}/get_analysis_config"
WS_TYPE_SET_ANALYSIS_CONFIG = f"{DOMAIN}/set_analysis_config"
WS_TYPE_SET_CAMERA_OBJECTS = f"{DOMAIN}/set_camera_objects"
WS_TYPE_GET_PEOPLE = f"{DOMAIN}/get_people"
WS_TYPE_ADD_PERSON = f"{DOMAIN}/add_person"
WS_TYPE_RENAME_PERSON = f"{DOMAIN}/rename_person"
WS_TYPE_DELETE_PERSON = f"{DOMAIN}/delete_person"
WS_TYPE_ADD_PERSON_EMBEDDING = f"{DOMAIN}/add_person_embedding"
WS_TYPE_ADD_NEGATIVE_SAMPLE = f"{DOMAIN}/add_negative_sample"
WS_TYPE_ADD_IGNORED_EMBEDDING = f"{DOMAIN}/add_ignored_embedding"
