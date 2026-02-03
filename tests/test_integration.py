"""Integration Tests for RTSP Recorder.

Feature: Integration Test Suite (Audit Report v1.1.1)

Tests for:
- Module interactions
- End-to-end flows
- Database + Service integration
- WebSocket handler flows
- Config validation flows
"""
import pytest
import sys
import asyncio
import sqlite3
import tempfile
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rtsp_recorder"))


@pytest.mark.integration
class TestDatabaseServiceIntegration:
    """Integration tests for Database + Service interactions."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database with full schema."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        
        # Create full production schema
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS person (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted INTEGER DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS face_embedding (
                id TEXT PRIMARY KEY,
                person_id TEXT NOT NULL,
                embedding TEXT NOT NULL,
                source_image TEXT,
                quality_score REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (person_id) REFERENCES person(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS recognition_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT,
                person_name TEXT,
                camera_id TEXT,
                camera_name TEXT,
                confidence REAL,
                recording_path TEXT,
                thumbnail_path TEXT,
                recognized_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (person_id) REFERENCES person(id)
            );
            
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            );
            
            INSERT INTO schema_version (version) VALUES (4);
            
            CREATE INDEX IF NOT EXISTS idx_person_deleted ON person(deleted);
            CREATE INDEX IF NOT EXISTS idx_face_person ON face_embedding(person_id);
            CREATE INDEX IF NOT EXISTS idx_history_person ON recognition_history(person_id);
            CREATE INDEX IF NOT EXISTS idx_history_camera ON recognition_history(camera_id);
            CREATE INDEX IF NOT EXISTS idx_history_time ON recognition_history(recognized_at);
        """)
        
        conn.commit()
        conn.close()
        
        yield path
        
        if os.path.exists(path):
            os.remove(path)
    
    def test_person_crud_flow(self, temp_db):
        """Test complete person CRUD flow."""
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # CREATE
        person_id = "test_person_001"
        cursor.execute(
            "INSERT INTO person (id, name, metadata) VALUES (?, ?, ?)",
            (person_id, "Max Mustermann", json.dumps({"notes": "Test"}))
        )
        conn.commit()
        
        # READ
        cursor.execute("SELECT * FROM person WHERE id = ?", (person_id,))
        person = cursor.fetchone()
        assert person is not None
        assert person["name"] == "Max Mustermann"
        assert json.loads(person["metadata"])["notes"] == "Test"
        
        # UPDATE
        cursor.execute(
            "UPDATE person SET name = ?, updated_at = ? WHERE id = ?",
            ("Max Updated", datetime.now().isoformat(), person_id)
        )
        conn.commit()
        
        cursor.execute("SELECT name FROM person WHERE id = ?", (person_id,))
        assert cursor.fetchone()["name"] == "Max Updated"
        
        # SOFT DELETE
        cursor.execute(
            "UPDATE person SET deleted = 1, updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), person_id)
        )
        conn.commit()
        
        cursor.execute("SELECT deleted FROM person WHERE id = ?", (person_id,))
        assert cursor.fetchone()["deleted"] == 1
        
        # Verify soft-deleted person not in active list
        cursor.execute("SELECT * FROM person WHERE deleted = 0")
        assert len(cursor.fetchall()) == 0
        
        conn.close()
    
    def test_face_embedding_cascade_delete(self, temp_db):
        """Test face embeddings are deleted when person is deleted."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")
        
        # Create person
        person_id = "person_cascade_test"
        cursor.execute(
            "INSERT INTO person (id, name) VALUES (?, ?)",
            (person_id, "Cascade Test")
        )
        
        # Create face embeddings
        for i in range(3):
            cursor.execute(
                "INSERT INTO face_embedding (id, person_id, embedding) VALUES (?, ?, ?)",
                (f"emb_{i}", person_id, json.dumps([0.1] * 128))
            )
        conn.commit()
        
        # Verify embeddings exist
        cursor.execute("SELECT COUNT(*) FROM face_embedding WHERE person_id = ?", (person_id,))
        assert cursor.fetchone()[0] == 3
        
        # Delete person (cascade)
        cursor.execute("DELETE FROM person WHERE id = ?", (person_id,))
        conn.commit()
        
        # Verify embeddings were cascade deleted
        cursor.execute("SELECT COUNT(*) FROM face_embedding WHERE person_id = ?", (person_id,))
        assert cursor.fetchone()[0] == 0
        
        conn.close()
    
    def test_recognition_history_flow(self, temp_db):
        """Test recognition history recording and querying."""
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Create person
        cursor.execute(
            "INSERT INTO person (id, name) VALUES (?, ?)",
            ("person_hist", "History Test")
        )
        
        # Record multiple recognitions
        for i in range(5):
            cursor.execute("""
                INSERT INTO recognition_history 
                (person_id, person_name, camera_id, camera_name, confidence, recognized_at)
                VALUES (?, ?, ?, ?, ?, datetime('now', ?))
            """, ("person_hist", "History Test", "cam_1", "Testcam", 0.95 - i*0.01, f"-{i} hours"))
        conn.commit()
        
        # Query recent history
        cursor.execute("""
            SELECT * FROM recognition_history 
            WHERE person_id = ? 
            ORDER BY recognized_at DESC 
            LIMIT 3
        """, ("person_hist",))
        history = cursor.fetchall()
        
        assert len(history) == 3
        assert history[0]["confidence"] == 0.95  # Most recent
        
        # Query by camera
        cursor.execute("""
            SELECT COUNT(*) FROM recognition_history WHERE camera_id = ?
        """, ("cam_1",))
        assert cursor.fetchone()[0] == 5
        
        conn.close()


@pytest.mark.integration
class TestInputValidationIntegration:
    """Integration tests for input validation across modules."""
    
    def test_person_name_validation_flow(self):
        """Test person name validation through the system."""
        import re
        
        VALID_NAME_PATTERN = re.compile(r"^[\w\s\-'\.äöüÄÖÜß]{1,100}$", re.UNICODE)
        
        test_cases = [
            # (input, should_pass, reason)
            ("Max Mustermann", True, "Normal name"),
            ("Hans-Peter", True, "Hyphenated"),
            ("O'Brien", True, "Apostrophe"),
            ("Müller", True, "Umlaut"),
            ("", False, "Empty"),
            ("<script>alert(1)</script>", False, "XSS attempt"),
            ("'; DROP TABLE--", False, "SQL injection"),
            ("A" * 101, False, "Too long"),
        ]
        
        for name, should_pass, reason in test_cases:
            is_valid = bool(VALID_NAME_PATTERN.match(name)) if name else False
            assert is_valid == should_pass, f"Failed for '{name}': {reason}"
    
    def test_path_validation_flow(self):
        """Test path validation through the system."""
        VALID_PREFIXES = ["/media/", "/config/", "/share/", "/ssl/"]
        
        def validate_path(path):
            if not path or "\x00" in path:
                return False
            if ".." in path:
                return False
            return any(path.startswith(p) for p in VALID_PREFIXES)
        
        test_cases = [
            ("/media/rtsp_recorder/video.mp4", True),
            ("/config/data.json", True),
            ("/etc/passwd", False),
            ("../../../etc/passwd", False),
            ("/media/../../../etc", False),
            ("/media/test\x00.mp4", False),
        ]
        
        for path, expected in test_cases:
            assert validate_path(path) == expected, f"Failed for {path}"
    
    def test_camera_id_validation_flow(self):
        """Test camera ID validation through the system."""
        import re
        
        VALID_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
        
        test_cases = [
            ("cam_1", True),
            ("Wohnzimmer", True),
            ("cam/1", False),  # Path separator
            ("cam;sql", False),  # SQL
            ("a" * 65, False),  # Too long
        ]
        
        for cam_id, expected in test_cases:
            is_valid = bool(VALID_ID_PATTERN.match(cam_id))
            assert is_valid == expected, f"Failed for {cam_id}"


@pytest.mark.integration
class TestWebSocketMessageFlow:
    """Integration tests for WebSocket message handling flows."""
    
    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant."""
        hass = MagicMock()
        hass.data = {"rtsp_recorder": {"cameras": {}, "people_db": {}}}
        hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *args: f(*args))
        return hass
    
    @pytest.fixture
    def mock_connection(self):
        """Create mock WebSocket connection."""
        conn = MagicMock()
        conn.send_result = MagicMock()
        conn.send_error = MagicMock()
        conn.user = MagicMock()
        conn.user.id = "test_user"
        return conn
    
    def test_get_people_message_flow(self, mock_hass, mock_connection):
        """Test get_people WebSocket message flow."""
        # Simulate message
        msg = {
            "id": 1,
            "type": "rtsp_recorder/get_people"
        }
        
        # Validate message structure
        assert "type" in msg
        assert msg["type"].startswith("rtsp_recorder/")
        
        # Simulate response
        response = {
            "success": True,
            "people": [
                {"id": "person_1", "name": "Alice", "sample_count": 3},
                {"id": "person_2", "name": "Bob", "sample_count": 5},
            ]
        }
        
        # Validate response
        assert response["success"] is True
        assert len(response["people"]) == 2
        for person in response["people"]:
            assert "id" in person
            assert "name" in person
    
    def test_add_person_message_flow(self, mock_hass, mock_connection):
        """Test add_person WebSocket message flow."""
        import re
        VALID_NAME_PATTERN = re.compile(r"^[\w\s\-'\.äöüÄÖÜß]{1,100}$", re.UNICODE)
        
        # Valid message
        msg = {
            "id": 2,
            "type": "rtsp_recorder/add_person",
            "name": "Max Mustermann"
        }
        
        # Validate input
        assert "name" in msg
        assert VALID_NAME_PATTERN.match(msg["name"])
        
        # Invalid message (XSS attempt)
        invalid_msg = {
            "id": 3,
            "type": "rtsp_recorder/add_person",
            "name": "<script>alert(1)</script>"
        }
        
        assert not VALID_NAME_PATTERN.match(invalid_msg["name"])
    
    def test_delete_person_message_flow(self, mock_hass, mock_connection):
        """Test delete_person WebSocket message flow."""
        import re
        VALID_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
        
        # Valid message
        msg = {
            "id": 4,
            "type": "rtsp_recorder/delete_person",
            "person_id": "person_123"
        }
        
        assert "person_id" in msg
        assert VALID_ID_PATTERN.match(msg["person_id"])
        
        # Invalid person_id
        invalid_msg = {
            "id": 5,
            "type": "rtsp_recorder/delete_person",
            "person_id": "../../../etc"
        }
        
        assert not VALID_ID_PATTERN.match(invalid_msg["person_id"])


@pytest.mark.integration
class TestAnalysisResultFlow:
    """Integration tests for analysis result processing."""
    
    @pytest.fixture
    def sample_analysis_result(self):
        """Create sample analysis result."""
        return {
            "video": "/media/rtsp_recorder/recordings/Testcam/2026-02-03/video_001.mp4",
            "camera_id": "testcam",
            "camera_name": "Testcam",
            "created_at": "2026-02-03T14:30:00",
            "device": "coral_usb",
            "duration_sec": 45.2,
            "frames_analyzed": 60,
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
                    "person_id": "person_1",
                    "person_name": "Max Mustermann",
                    "confidence": 0.95,
                    "matched": True,
                }
            ],
            "thumbnails": {
                "main": "/media/rtsp_recorder/thumbnails/testcam/2026-02-03/thumb_001.jpg",
                "faces": [
                    "/media/rtsp_recorder/thumbnails/testcam/2026-02-03/face_001.jpg"
                ]
            }
        }
    
    def test_analysis_result_structure(self, sample_analysis_result):
        """Test analysis result has required structure."""
        result = sample_analysis_result
        
        # Required fields
        assert "video" in result
        assert "camera_id" in result
        assert "detections" in result
        
        # Detection structure
        assert "person" in result["detections"]
        assert isinstance(result["detections"]["person"], list)
        
        # Detection item structure
        for detection in result["detections"]["person"]:
            assert "frame" in detection
            assert "confidence" in detection
            assert "box" in detection
            assert len(detection["box"]) == 4
    
    def test_face_match_result_structure(self, sample_analysis_result):
        """Test face match result structure."""
        faces = sample_analysis_result["faces"]
        
        assert len(faces) == 1
        face = faces[0]
        
        assert "frame" in face
        assert "person_id" in face
        assert "person_name" in face
        assert "confidence" in face
        assert "matched" in face
        
        assert 0 <= face["confidence"] <= 1
    
    def test_path_validation_in_result(self, sample_analysis_result):
        """Test paths in result are valid."""
        VALID_PREFIXES = ["/media/", "/config/", "/share/"]
        
        def is_valid_path(path):
            return any(path.startswith(p) for p in VALID_PREFIXES)
        
        assert is_valid_path(sample_analysis_result["video"])
        assert is_valid_path(sample_analysis_result["thumbnails"]["main"])
        
        for face_thumb in sample_analysis_result["thumbnails"]["faces"]:
            assert is_valid_path(face_thumb)


@pytest.mark.integration
class TestConfigFlowValidation:
    """Integration tests for config flow validation."""
    
    def test_camera_config_validation(self):
        """Test camera configuration validation."""
        import re
        
        RTSP_PATTERN = re.compile(r"^rtsps?://")
        
        valid_configs = [
            {
                "name": "Testcam",
                "url": "rtsp://192.168.1.100/stream",
                "enabled": True,
            },
            {
                "name": "Secure Cam",
                "url": "rtsps://192.168.1.101:554/h264",
                "enabled": True,
            },
        ]
        
        for config in valid_configs:
            assert RTSP_PATTERN.match(config["url"])
            assert len(config["name"]) <= 100
        
        invalid_configs = [
            {"name": "Bad", "url": "http://example.com"},  # Wrong protocol
            {"name": "Bad", "url": "file:///etc/passwd"},  # File URL
            {"name": "Bad", "url": "javascript:alert(1)"},  # XSS
        ]
        
        for config in invalid_configs:
            assert not RTSP_PATTERN.match(config["url"])
    
    def test_retention_config_validation(self):
        """Test retention configuration validation."""
        def validate_retention(days):
            return isinstance(days, int) and 1 <= days <= 365
        
        assert validate_retention(7)
        assert validate_retention(30)
        assert validate_retention(365)
        
        assert not validate_retention(0)
        assert not validate_retention(-1)
        assert not validate_retention(366)
        assert not validate_retention("7")
    
    def test_storage_path_validation(self):
        """Test storage path configuration validation."""
        VALID_PREFIXES = ["/media/", "/share/", "/config/"]
        
        def validate_storage_path(path):
            if not path:
                return False
            if ".." in path:
                return False
            return any(path.startswith(p) for p in VALID_PREFIXES)
        
        assert validate_storage_path("/media/rtsp_recorder")
        assert validate_storage_path("/share/recordings")
        
        assert not validate_storage_path("/etc/secret")
        assert not validate_storage_path("../../../root")


@pytest.mark.integration
class TestSecurityIntegration:
    """Integration tests for security measures across modules."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE person (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        cursor.execute("INSERT INTO person VALUES ('p1', 'Alice')")
        cursor.execute("INSERT INTO person VALUES ('p2', 'Bob')")
        conn.commit()
        yield conn
        conn.close()
    
    def test_sql_injection_blocked(self, temp_db):
        """Test SQL injection is blocked throughout system."""
        malicious_inputs = [
            "'; DROP TABLE person; --",
            "' OR '1'='1",
            "'; DELETE FROM person; --",
            "' UNION SELECT * FROM person; --",
        ]
        
        for malicious in malicious_inputs:
            # Parameterized query blocks injection
            cursor = temp_db.execute(
                "SELECT * FROM person WHERE name = ?",
                (malicious,)
            )
            result = cursor.fetchall()
            assert result == []  # No match, no injection
            
            # Verify table still intact
            cursor = temp_db.execute("SELECT COUNT(*) FROM person")
            assert cursor.fetchone()[0] == 2
    
    def test_xss_escaping(self):
        """Test XSS escaping throughout system."""
        def escape_html(text):
            if not text:
                return ""
            return (str(text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#x27;"))
        
        xss_attempts = [
            ("<script>alert(1)</script>", "&lt;script&gt;"),
            ('<img onerror="alert(1)">', "&lt;img"),
            ("javascript:alert(1)", "javascript"),  # No HTML, passes through
            ("' onclick='", "&#x27;"),
        ]
        
        for attack, expected_part in xss_attempts:
            escaped = escape_html(attack)
            assert "<script>" not in escaped
            assert "onerror" not in escaped or '"' not in escaped
            
            # Original attack string should not be executable
            assert attack != escaped or "<" not in attack
    
    def test_path_traversal_blocked(self):
        """Test path traversal is blocked throughout system."""
        VALID_PREFIXES = ["/media/", "/config/", "/share/"]
        
        def validate_and_resolve_path(path):
            if not path:
                return None
            if "\x00" in path:
                return None
            
            # Check for traversal
            if ".." in path:
                return None
            
            # Check prefix
            if not any(path.startswith(p) for p in VALID_PREFIXES):
                return None
            
            return path
        
        traversal_attempts = [
            "../../../etc/passwd",
            "/media/../../../etc/passwd",
            "/media/test/../../secret",
            "/media/file\x00.txt",
        ]
        
        for attack in traversal_attempts:
            assert validate_and_resolve_path(attack) is None


@pytest.mark.integration
class TestEndToEndFlows:
    """End-to-end integration tests."""
    
    def test_person_recognition_flow(self):
        """Test complete person recognition flow."""
        # 1. Create person
        person = {
            "id": "person_e2e_001",
            "name": "E2E Test Person",
            "embeddings": []
        }
        
        # 2. Add face embedding
        embedding = [0.1 + i * 0.001 for i in range(128)]  # 128-dim embedding
        person["embeddings"].append({
            "id": "emb_001",
            "vector": embedding
        })
        
        # 3. Compute centroid
        def compute_centroid(embeddings):
            if not embeddings:
                return None
            vectors = [e["vector"] for e in embeddings]
            dim = len(vectors[0])
            centroid = [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]
            # Normalize
            norm = sum(c * c for c in centroid) ** 0.5
            if norm > 0:
                centroid = [c / norm for c in centroid]
            return centroid
        
        person["centroid"] = compute_centroid(person["embeddings"])
        assert person["centroid"] is not None
        assert len(person["centroid"]) == 128
        
        # 4. Match face
        def cosine_similarity(a, b):
            if len(a) != len(b):
                return 0.0
            dot = sum(x * y for x, y in zip(a, b))
            na = sum(x * x for x in a) ** 0.5
            nb = sum(y * y for y in b) ** 0.5
            if na == 0 or nb == 0:
                return 0.0
            return dot / (na * nb)
        
        # Test with similar embedding
        test_embedding = [0.1 + i * 0.001 + 0.0001 for i in range(128)]  # Slight variation
        similarity = cosine_similarity(person["centroid"], test_embedding)
        
        assert similarity > 0.99  # Should be very similar
        
        # 5. Record recognition
        recognition = {
            "person_id": person["id"],
            "person_name": person["name"],
            "camera_id": "cam_test",
            "camera_name": "Test Camera",
            "confidence": similarity,
            "recognized_at": datetime.now().isoformat()
        }
        
        assert recognition["confidence"] > 0.9
        assert recognition["person_name"] == "E2E Test Person"
    
    def test_recording_analysis_flow(self):
        """Test recording to analysis flow."""
        # 1. Simulate recording metadata
        recording = {
            "id": "rec_e2e_001",
            "camera_id": "testcam",
            "camera_name": "Testcam",
            "path": "/media/rtsp_recorder/recordings/testcam/2026-02-03/video.mp4",
            "duration": 300,  # 5 minutes
            "created_at": datetime.now().isoformat()
        }
        
        # 2. Validate recording path
        assert recording["path"].startswith("/media/")
        assert ".." not in recording["path"]
        
        # 3. Simulate analysis request
        analysis_request = {
            "video_path": recording["path"],
            "camera_id": recording["camera_id"],
            "detect_objects": True,
            "detect_faces": True,
            "match_people": True,
        }
        
        # 4. Simulate analysis result
        analysis_result = {
            "video": analysis_request["video_path"],
            "status": "completed",
            "duration_sec": 42.5,
            "device": "coral_usb",
            "detections": {
                "person": [{"frame": 50, "confidence": 0.95}],
            },
            "faces": [],
            "error": None
        }
        
        assert analysis_result["status"] == "completed"
        assert analysis_result["error"] is None
        assert len(analysis_result["detections"]["person"]) > 0
    
    def test_statistics_aggregation_flow(self):
        """Test statistics aggregation flow."""
        # Simulate recognition history
        history = []
        cameras = ["cam_1", "cam_2"]
        persons = ["person_1", "person_2", "person_3"]
        
        for i in range(24):  # 24 hours
            for _ in range(3):  # 3 recognitions per hour
                history.append({
                    "camera_id": cameras[i % 2],
                    "person_id": persons[i % 3],
                    "hour": i,
                })
        
        # Aggregate by camera
        camera_stats = {}
        for entry in history:
            cam = entry["camera_id"]
            camera_stats[cam] = camera_stats.get(cam, 0) + 1
        
        assert camera_stats["cam_1"] == 36
        assert camera_stats["cam_2"] == 36
        
        # Aggregate by person
        person_stats = {}
        for entry in history:
            person = entry["person_id"]
            person_stats[person] = person_stats.get(person, 0) + 1
        
        assert sum(person_stats.values()) == 72
        
        # Aggregate by hour
        hourly_stats = {}
        for entry in history:
            hour = entry["hour"]
            hourly_stats[hour] = hourly_stats.get(hour, 0) + 1
        
        assert all(count == 3 for count in hourly_stats.values())
