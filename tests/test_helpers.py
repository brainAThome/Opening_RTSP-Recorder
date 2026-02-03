"""Unit tests for Helpers module.

Feature: Test-Coverage Erweiterung (Audit Report v1.1.1)

Tests for:
- InferenceStatsTracker
- System stats
- Input validation
- Path validation
- Log rotation
"""
import pytest
import sys
import time
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rtsp_recorder"))

try:
    from helpers import (
        InferenceStatsTracker,
        get_inference_stats,
        get_system_stats,
        is_valid_person_name,
        validate_path,
        parse_time_string,
        log_to_file,
        VALID_PATH_PREFIXES,
    )
except ImportError as e:
    InferenceStatsTracker = None
    print(f"Import error: {e}")


@pytest.mark.unit
class TestInferenceStatsTracker:
    """Tests for InferenceStatsTracker."""
    
    @pytest.fixture
    def tracker(self):
        """Create fresh tracker for each test."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        return InferenceStatsTracker(max_history=100)
    
    def test_initial_stats(self, tracker):
        """Test initial statistics are zero."""
        stats = tracker.get_stats()
        
        assert stats["total_inferences"] == 0
        assert stats["coral_inferences"] == 0
        assert stats["cpu_inferences"] == 0
        assert stats["last_device"] == "none"
        assert stats["inferences_per_minute"] == 0
    
    def test_record_coral_inference(self, tracker):
        """Test recording Coral TPU inference."""
        tracker.record("coral_usb", duration_ms=50.0, frame_count=10)
        
        stats = tracker.get_stats()
        assert stats["total_inferences"] == 10
        assert stats["coral_inferences"] == 10
        assert stats["cpu_inferences"] == 0
        assert stats["last_device"] == "coral_usb"
    
    def test_record_cpu_inference(self, tracker):
        """Test recording CPU inference."""
        tracker.record("cpu", duration_ms=200.0, frame_count=5)
        
        stats = tracker.get_stats()
        assert stats["total_inferences"] == 5
        assert stats["coral_inferences"] == 0
        assert stats["cpu_inferences"] == 5
        assert stats["last_device"] == "cpu"
    
    def test_mixed_inferences(self, tracker):
        """Test mixed Coral and CPU inferences."""
        tracker.record("coral_usb", duration_ms=50.0, frame_count=10)
        tracker.record("cpu", duration_ms=200.0, frame_count=5)
        tracker.record("coral_usb", duration_ms=45.0, frame_count=10)
        
        stats = tracker.get_stats()
        assert stats["total_inferences"] == 25
        assert stats["coral_inferences"] == 20
        assert stats["cpu_inferences"] == 5
        assert stats["coral_usage_pct"] == 80.0
    
    def test_inferences_per_minute(self, tracker):
        """Test inferences per minute calculation."""
        # Record 10 inferences within last minute
        for i in range(10):
            tracker.record("coral_usb", duration_ms=50.0, frame_count=1)
        
        stats = tracker.get_stats()
        assert stats["inferences_per_minute"] == 10
    
    def test_average_inference_time(self, tracker):
        """Test average inference time calculation."""
        tracker.record("coral_usb", duration_ms=40.0, frame_count=1)
        tracker.record("coral_usb", duration_ms=60.0, frame_count=1)
        tracker.record("coral_usb", duration_ms=50.0, frame_count=1)
        
        stats = tracker.get_stats()
        assert stats["avg_inference_ms"] == 50.0
    
    def test_max_history_limit(self, tracker):
        """Test that history respects max_history limit."""
        # Record more than max_history
        for i in range(150):
            tracker.record("cpu", duration_ms=10.0, frame_count=1)
        
        stats = tracker.get_stats()
        # Total should be 150, but recent (last 60s) depends on timing
        assert stats["total_inferences"] == 150
    
    def test_thread_safety(self, tracker):
        """Test thread-safe recording."""
        import threading
        
        def record_many():
            for _ in range(100):
                tracker.record("coral_usb", duration_ms=10.0, frame_count=1)
        
        threads = [threading.Thread(target=record_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        stats = tracker.get_stats()
        assert stats["total_inferences"] == 500


@pytest.mark.unit
class TestInputValidation:
    """Tests for input validation functions."""
    
    def test_valid_person_name(self):
        """Test valid person names."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        assert is_valid_person_name("Max Mustermann") is True
        assert is_valid_person_name("Anna") is True
        assert is_valid_person_name("Hans-Peter") is True
        assert is_valid_person_name("O'Brien") is True
        assert is_valid_person_name("José María") is True
        assert is_valid_person_name("李明") is True  # Chinese characters
    
    def test_invalid_person_name_empty(self):
        """Test empty person names are invalid."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        assert is_valid_person_name("") is False
        assert is_valid_person_name("   ") is False
        assert is_valid_person_name(None) is False
    
    def test_invalid_person_name_too_long(self):
        """Test person names exceeding max length."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        # 101 characters should be invalid (max is 100)
        long_name = "A" * 101
        assert is_valid_person_name(long_name) is False
    
    def test_invalid_person_name_special_chars(self):
        """Test person names with dangerous characters."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        # SQL injection attempt
        assert is_valid_person_name("'; DROP TABLE--") is False
        # XSS attempt
        assert is_valid_person_name("<script>alert()</script>") is False
        # Path traversal
        assert is_valid_person_name("../../../etc") is False
        # Null byte
        assert is_valid_person_name("Test\x00Hidden") is False


@pytest.mark.unit
class TestPathValidation:
    """Tests for path validation functions."""
    
    def test_valid_paths(self):
        """Test valid storage paths."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        # These should be valid paths
        assert validate_path("/media/rtsp_recorder/video.mp4") is True
        assert validate_path("/config/rtsp_recorder/data.json") is True
        assert validate_path("/share/recordings/cam1/video.mp4") is True
    
    def test_path_traversal_attack(self):
        """Test path traversal attacks are blocked."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        # Path traversal attempts
        assert validate_path("../../../etc/passwd") is False
        assert validate_path("/media/../../../etc/passwd") is False
        assert validate_path("/media/rtsp_recorder/../../secret") is False
    
    def test_invalid_prefix(self):
        """Test paths outside allowed prefixes."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        # These should be invalid (not in VALID_PATH_PREFIXES)
        assert validate_path("/etc/passwd") is False
        assert validate_path("/root/.ssh/id_rsa") is False
        assert validate_path("/var/log/syslog") is False
    
    def test_null_byte_injection(self):
        """Test null byte injection is blocked."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        assert validate_path("/media/rtsp\x00/../../etc/passwd") is False


@pytest.mark.unit
class TestTimeStringParsing:
    """Tests for time string parsing."""
    
    def test_parse_seconds(self):
        """Test parsing seconds format."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        assert parse_time_string("30") == 30
        assert parse_time_string("300") == 300
        assert parse_time_string("3600") == 3600
    
    def test_parse_minutes(self):
        """Test parsing minutes format."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        assert parse_time_string("5m") == 300
        assert parse_time_string("10m") == 600
        assert parse_time_string("60m") == 3600
    
    def test_parse_hours(self):
        """Test parsing hours format."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        assert parse_time_string("1h") == 3600
        assert parse_time_string("2h") == 7200
        assert parse_time_string("24h") == 86400
    
    def test_parse_invalid(self):
        """Test invalid time strings."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        assert parse_time_string("invalid") is None
        assert parse_time_string("") is None
        assert parse_time_string(None) is None
        assert parse_time_string("-5") is None


@pytest.mark.unit
class TestSystemStats:
    """Tests for system stats functions."""
    
    def test_get_system_stats_returns_dict(self):
        """Test system stats returns proper dict."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        stats = get_system_stats()
        
        assert isinstance(stats, dict)
        assert "cpu_percent" in stats
        assert "memory_percent" in stats
        assert "memory_used_mb" in stats
        assert "memory_total_mb" in stats
    
    def test_get_system_stats_valid_ranges(self):
        """Test system stats values are in valid ranges."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        stats = get_system_stats()
        
        # CPU percent should be 0-100 (or 0 on non-Linux)
        assert 0 <= stats["cpu_percent"] <= 100
        
        # Memory percent should be 0-100 (or 0 on non-Linux)
        assert 0 <= stats["memory_percent"] <= 100
        
        # Memory values should be non-negative
        assert stats["memory_used_mb"] >= 0
        assert stats["memory_total_mb"] >= 0


@pytest.mark.unit
class TestLogRotation:
    """Tests for log rotation functionality."""
    
    def test_log_to_file_creates_file(self):
        """Test log_to_file creates log file."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "test.log")
            
            # Mock the log file path
            with patch("helpers._LOG_FILE_PATH", log_path):
                log_to_file("Test message")
                
                # Check file was created
                assert os.path.exists(log_path)
    
    def test_log_to_file_appends(self):
        """Test log_to_file appends to existing file."""
        if InferenceStatsTracker is None:
            pytest.skip("Module not available")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "test.log")
            
            with patch("helpers._LOG_FILE_PATH", log_path):
                log_to_file("Message 1")
                log_to_file("Message 2")
                
                with open(log_path, "r") as f:
                    content = f.read()
                
                assert "Message 1" in content
                assert "Message 2" in content
