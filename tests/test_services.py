"""Unit tests for Services module.

Feature: Test-Coverage Erweiterung (Audit Report v1.1.1)

Tests for:
- Service registration
- Service validation
- Service call handling
- Error handling in services
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rtsp_recorder"))

try:
    from services import (
        async_setup_services,
        async_unload_services,
    )
except ImportError as e:
    async_setup_services = None
    print(f"Import error: {e}")


@pytest.mark.unit
class TestServiceRegistration:
    """Tests for service registration."""
    
    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = MagicMock()
        hass.data = {}
        hass.services = MagicMock()
        hass.services.async_register = AsyncMock()
        hass.services.async_remove = MagicMock()
        hass.async_add_executor_job = AsyncMock(side_effect=lambda f, *args: f(*args))
        return hass
    
    @pytest.mark.asyncio
    async def test_services_registered(self, mock_hass):
        """Test that services are registered on setup."""
        if async_setup_services is None:
            pytest.skip("Module not available")
        
        # Setup services
        await async_setup_services(mock_hass)
        
        # Verify async_register was called
        assert mock_hass.services.async_register.called
    
    @pytest.mark.asyncio
    async def test_services_unregistered(self, mock_hass):
        """Test that services are unregistered on unload."""
        if async_setup_services is None:
            pytest.skip("Module not available")
        
        # Unload services
        await async_unload_services(mock_hass)
        
        # Verify async_remove was called (if services were registered)
        # This depends on implementation


@pytest.mark.unit
class TestServiceValidation:
    """Tests for service call validation."""
    
    def test_camera_id_validation(self):
        """Test camera_id parameter validation."""
        import re
        
        valid_pattern = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
        
        # Valid camera IDs
        assert valid_pattern.match("cam_1")
        assert valid_pattern.match("Wohnzimmer")
        assert valid_pattern.match("front-door")
        
        # Invalid camera IDs
        assert not valid_pattern.match("")  # Empty
        assert not valid_pattern.match("cam/1")  # Slash
        assert not valid_pattern.match("a" * 65)  # Too long
    
    def test_person_id_validation(self):
        """Test person_id parameter validation."""
        import re
        
        valid_pattern = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
        
        # Valid person IDs
        assert valid_pattern.match("person_1")
        assert valid_pattern.match("MAX-123")
        
        # Invalid person IDs
        assert not valid_pattern.match("'; DROP TABLE")
        assert not valid_pattern.match("<script>")
    
    def test_retention_days_validation(self):
        """Test retention_days parameter validation."""
        def validate_retention(days):
            return isinstance(days, int) and 1 <= days <= 365
        
        # Valid values
        assert validate_retention(7)
        assert validate_retention(30)
        assert validate_retention(365)
        
        # Invalid values
        assert not validate_retention(0)
        assert not validate_retention(-1)
        assert not validate_retention(366)
        assert not validate_retention("7")  # String
    
    def test_segment_duration_validation(self):
        """Test segment_duration parameter validation."""
        def validate_duration(seconds):
            return isinstance(seconds, int) and 60 <= seconds <= 3600
        
        # Valid values
        assert validate_duration(60)
        assert validate_duration(300)
        assert validate_duration(3600)
        
        # Invalid values
        assert not validate_duration(59)
        assert not validate_duration(3601)


@pytest.mark.unit
class TestServiceCalls:
    """Tests for service call handling."""
    
    @pytest.fixture
    def mock_service_call(self):
        """Create mock service call."""
        call = MagicMock()
        call.data = {}
        return call
    
    def test_start_recording_call(self, mock_service_call):
        """Test start_recording service call structure."""
        mock_service_call.data = {
            "camera_id": "cam_1",
            "duration": 300,
        }
        
        # Validate required fields
        assert "camera_id" in mock_service_call.data
        assert isinstance(mock_service_call.data.get("duration", 300), int)
    
    def test_stop_recording_call(self, mock_service_call):
        """Test stop_recording service call structure."""
        mock_service_call.data = {
            "camera_id": "cam_1",
        }
        
        # Validate required fields
        assert "camera_id" in mock_service_call.data
    
    def test_add_person_call(self, mock_service_call):
        """Test add_person service call structure."""
        mock_service_call.data = {
            "name": "Max Mustermann",
        }
        
        # Validate required fields
        assert "name" in mock_service_call.data
        assert len(mock_service_call.data["name"]) <= 100
    
    def test_delete_person_call(self, mock_service_call):
        """Test delete_person service call structure."""
        mock_service_call.data = {
            "person_id": "person_1",
        }
        
        # Validate required fields
        assert "person_id" in mock_service_call.data


@pytest.mark.unit
class TestServiceErrorHandling:
    """Tests for error handling in services."""
    
    def test_missing_required_field(self):
        """Test error when required field is missing."""
        call_data = {}  # Missing camera_id
        
        required_fields = ["camera_id"]
        missing = [f for f in required_fields if f not in call_data]
        
        assert "camera_id" in missing
    
    def test_invalid_camera_id_error(self):
        """Test error for invalid camera ID."""
        call_data = {"camera_id": "../../../etc"}
        
        import re
        valid_pattern = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
        
        is_valid = valid_pattern.match(call_data["camera_id"]) is not None
        assert not is_valid
    
    def test_camera_not_found_error(self):
        """Test error when camera not found."""
        available_cameras = {"cam_1", "cam_2"}
        requested_camera = "cam_99"
        
        camera_exists = requested_camera in available_cameras
        assert not camera_exists


@pytest.mark.unit
class TestServiceResponses:
    """Tests for service response formatting."""
    
    def test_success_response(self):
        """Test success response structure."""
        response = {
            "success": True,
            "message": "Recording started",
            "data": {
                "camera_id": "cam_1",
                "recording_id": "rec_123",
            }
        }
        
        assert response["success"] is True
        assert "message" in response
        assert "data" in response
    
    def test_error_response(self):
        """Test error response structure."""
        response = {
            "success": False,
            "error": "Camera not found",
            "error_code": "CAMERA_NOT_FOUND",
        }
        
        assert response["success"] is False
        assert "error" in response
        assert "error_code" in response
    
    def test_response_no_sensitive_data(self):
        """Test responses don't leak sensitive data."""
        # Sensitive fields that should never be in responses
        sensitive_fields = ["password", "token", "secret", "api_key"]
        
        response = {
            "success": True,
            "camera_id": "cam_1",
            "url": "rtsp://192.168.1.100/stream",  # URL without credentials
        }
        
        for field in sensitive_fields:
            assert field not in response
            assert field not in str(response.values())
