"""Pytest configuration and fixtures for RTSP Recorder tests.

Feature: MED-001 Unit Test Framework (Audit Report v1.1.0)
"""
import asyncio
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===== Pytest Configuration =====

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "ha: Home Assistant integration tests")
    config.addinivalue_line("markers", "slow: Slow tests")
    config.addinivalue_line("markers", "asyncio: Async tests")
    # Ensure pytest-asyncio can handle async fixtures from HA test plugin
    try:
        import pytest_homeassistant_custom_component  # noqa: F401
        if getattr(config.option, "asyncio_mode", None) in (None, "strict"):
            config.option.asyncio_mode = "auto"
    except Exception:
        pass


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ===== Mock Fixtures =====

@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.config.path = MagicMock(return_value="/config")
    hass.data = {}
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *args: f(*args))
    return hass


@pytest.fixture
def mock_connection():
    """Create a mock WebSocket connection."""
    connection = MagicMock()
    connection.send_result = MagicMock()
    connection.send_error = MagicMock()
    connection.user = MagicMock()
    connection.user.id = "test_user_123"
    return connection


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "cameras": [],
        "storage_path": "/media/rtsp_recorder",
        "retention_days": 7,
    }
    entry.options = {}
    return entry


# ===== Database Fixtures =====

@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_rtsp_recorder.db"


@pytest.fixture
def temp_db(temp_db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Create a temporary test database with schema."""
    conn = sqlite3.connect(str(temp_db_path))
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS persons (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS face_samples (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            image_path TEXT NOT NULL,
            embedding BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (person_id) REFERENCES persons(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recognition_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT,
            person_name TEXT,
            camera_id TEXT,
            camera_name TEXT,
            confidence REAL,
            recording_path TEXT,
            thumbnail_path TEXT,
            recognized_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            camera_id TEXT,
            path TEXT NOT NULL,
            thumbnail_path TEXT,
            duration INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    
    yield conn
    
    conn.close()
    temp_db_path.unlink(missing_ok=True)


@pytest.fixture
def populated_db(temp_db: sqlite3.Connection) -> sqlite3.Connection:
    """Create a database with sample data."""
    cursor = temp_db.cursor()
    
    # Add sample cameras
    cursor.execute(
        "INSERT INTO cameras (id, name, url) VALUES (?, ?, ?)",
        ("cam_1", "Testcam", "rtsp://192.168.1.100/stream")
    )
    cursor.execute(
        "INSERT INTO cameras (id, name, url) VALUES (?, ?, ?)",
        ("cam_2", "Flur", "rtsp://192.168.1.101/stream")
    )
    
    # Add sample persons
    cursor.execute(
        "INSERT INTO persons (id, name) VALUES (?, ?)",
        ("person_1", "Max Mustermann")
    )
    cursor.execute(
        "INSERT INTO persons (id, name) VALUES (?, ?)",
        ("person_2", "Anna Beispiel")
    )
    
    # Add sample recognition history
    cursor.execute(
        """INSERT INTO recognition_history 
           (person_id, person_name, camera_id, camera_name, confidence, recognized_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        ("person_1", "Max Mustermann", "cam_1", "Testcam", 0.95)
    )
    
    temp_db.commit()
    
    return temp_db


# ===== File System Fixtures =====

@pytest.fixture
def temp_storage(tmp_path: Path) -> Path:
    """Create a temporary storage directory structure."""
    storage = tmp_path / "rtsp_recorder"
    storage.mkdir()
    
    # Create subdirectories
    (storage / "recordings").mkdir()
    (storage / "thumbnails").mkdir()
    (storage / "analysis").mkdir()
    (storage / "faces").mkdir()
    
    return storage


@pytest.fixture
def sample_video_path(temp_storage: Path) -> Path:
    """Create a sample video file path."""
    video_path = temp_storage / "recordings" / "Testcam" / "2026-02-01" / "test_video.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create empty file for testing
    video_path.touch()
    
    return video_path


# ===== Helper Fixtures =====

@pytest.fixture
def sample_camera_config() -> dict:
    """Sample camera configuration."""
    return {
        "id": "test_cam",
        "name": "Test Kamera",
        "url": "rtsp://192.168.1.100:554/stream",
        "enabled": True,
        "record_audio": False,
        "segment_duration": 300,
    }


@pytest.fixture
def sample_person() -> dict:
    """Sample person data."""
    return {
        "id": "person_test_123",
        "name": "Test Person",
        "samples": [],
    }


@pytest.fixture
def sample_analysis_result() -> dict:
    """Sample analysis result."""
    return {
        "video": "/media/rtsp_recorder/recordings/Testcam/2026-02-01/video_001.mp4",
        "created_at": "2026-02-01T14:30:00",
        "device": "cpu",
        "duration_sec": 45.2,
        "detections": {
            "person": [
                {"frame": 100, "confidence": 0.92, "box": [100, 200, 300, 400]},
                {"frame": 150, "confidence": 0.88, "box": [110, 210, 310, 410]},
            ],
            "car": [
                {"frame": 200, "confidence": 0.85, "box": [50, 100, 200, 300]},
            ],
        },
        "faces": [
            {
                "frame": 100,
                "person_name": "Max Mustermann",
                "confidence": 0.95,
                "matched": True,
            }
        ],
    }
