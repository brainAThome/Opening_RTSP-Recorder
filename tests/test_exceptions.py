"""Unit tests for Exceptions module.

Feature: MED-001 Unit Test Framework (Audit Report v1.1.0)
"""
import pytest
import sys
from pathlib import Path

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rtsp_recorder"))

try:
    from exceptions import (
        RTSPRecorderError,
        ConfigurationError,
        InvalidConfigError,
        MissingConfigError,
        DatabaseError,
        DatabaseConnectionError,
        DatabaseQueryError,
        MigrationError,
        RecordingError,
        CameraConnectionError,
        PersonNotFoundError,
        ValidationError,
        handle_exception,
    )
except ImportError:
    RTSPRecorderError = None


@pytest.mark.unit
class TestRTSPRecorderError:
    """Tests for base RTSPRecorderError."""
    
    def test_basic_error(self):
        """Test basic error creation."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = RTSPRecorderError("Test error message")
        
        assert error.message == "Test error message"
        assert error.details == {}
        assert str(error) == "Test error message"
    
    def test_error_with_details(self):
        """Test error with details."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        details = {"key": "value", "count": 42}
        error = RTSPRecorderError("Test error", details)
        
        assert error.details == details
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = RTSPRecorderError("Test error", {"info": "test"})
        result = error.to_dict()
        
        assert result["error"] == "RTSPRecorderError"
        assert result["message"] == "Test error"
        assert result["details"] == {"info": "test"}


@pytest.mark.unit
class TestConfigurationErrors:
    """Tests for configuration errors."""
    
    def test_invalid_config_error(self):
        """Test InvalidConfigError."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = InvalidConfigError("retention_days", -5, "Must be positive")
        
        assert "retention_days" in error.message
        assert error.details["key"] == "retention_days"
        assert error.details["value"] == "-5"
        assert error.details["reason"] == "Must be positive"
    
    def test_missing_config_error(self):
        """Test MissingConfigError."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = MissingConfigError("storage_path")
        
        assert "storage_path" in error.message
        assert error.details["key"] == "storage_path"


@pytest.mark.unit
class TestDatabaseErrors:
    """Tests for database errors."""
    
    def test_connection_error(self):
        """Test DatabaseConnectionError."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = DatabaseConnectionError("/path/to/db.sqlite", "Permission denied")
        
        assert "/path/to/db.sqlite" in error.message
        assert "Permission denied" in error.message
        assert error.details["path"] == "/path/to/db.sqlite"
    
    def test_query_error(self):
        """Test DatabaseQueryError."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = DatabaseQueryError("INSERT", "Constraint violation")
        
        assert "INSERT" in error.message
        assert error.details["operation"] == "INSERT"
    
    def test_migration_error(self):
        """Test MigrationError."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = MigrationError(1, 2, "Column already exists")
        
        assert "v1" in error.message
        assert "v2" in error.message
        assert error.details["from_version"] == 1
        assert error.details["to_version"] == 2


@pytest.mark.unit
class TestRecordingErrors:
    """Tests for recording errors."""
    
    def test_camera_connection_error(self):
        """Test CameraConnectionError."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = CameraConnectionError(
            "Wohnzimmer", 
            "rtsp://192.168.1.100/stream", 
            "Connection timeout"
        )
        
        assert "Wohnzimmer" in error.message
        assert error.details["camera"] == "Wohnzimmer"
        assert error.details["url"] == "rtsp://192.168.1.100/stream"


@pytest.mark.unit
class TestPersonErrors:
    """Tests for person database errors."""
    
    def test_person_not_found(self):
        """Test PersonNotFoundError."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = PersonNotFoundError("person_123")
        
        assert "person_123" in error.message
        assert error.details["person_id"] == "person_123"


@pytest.mark.unit
class TestAPIErrors:
    """Tests for API errors."""
    
    def test_validation_error(self):
        """Test ValidationError."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = ValidationError("name", "Cannot be empty")
        
        assert "name" in error.message
        assert error.details["field"] == "name"
        assert error.details["reason"] == "Cannot be empty"


@pytest.mark.unit
class TestHandleException:
    """Tests for handle_exception utility."""
    
    def test_handles_custom_exception(self):
        """Test handling custom RTSP exception."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        exc = ValidationError("test_field", "Invalid value")
        result = handle_exception(exc, "test context")
        
        assert result["error"] == "ValidationError"
        assert "test_field" in result["message"]
    
    def test_handles_generic_exception(self):
        """Test handling generic Python exception."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        exc = ValueError("Something went wrong")
        result = handle_exception(exc, "processing data")
        
        assert result["error"] == "ValueError"
        assert result["message"] == "Something went wrong"
        assert result["details"]["context"] == "processing data"
    
    def test_handles_exception_without_context(self):
        """Test handling exception without context."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        exc = RuntimeError("Error")
        result = handle_exception(exc)
        
        assert result["error"] == "RuntimeError"
        assert result["details"] == {}


@pytest.mark.unit
class TestExceptionInheritance:
    """Tests for exception inheritance."""
    
    def test_config_error_is_rtsp_error(self):
        """Test ConfigurationError inherits from RTSPRecorderError."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = InvalidConfigError("key", "value", "reason")
        
        assert isinstance(error, RTSPRecorderError)
        assert isinstance(error, ConfigurationError)
    
    def test_database_error_is_rtsp_error(self):
        """Test DatabaseError inherits from RTSPRecorderError."""
        if RTSPRecorderError is None:
            pytest.skip("Module not available")
            
        error = DatabaseQueryError("SELECT", "Error")
        
        assert isinstance(error, RTSPRecorderError)
        assert isinstance(error, DatabaseError)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
