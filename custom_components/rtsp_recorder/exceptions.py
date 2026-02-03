"""Custom exceptions for RTSP Recorder.

This module defines specific exception types for better error handling
and more informative error messages.

Security Fix: HIGH-002 Specific Exception Handling (Audit Report v1.1.0)
"""
from typing import Any


class RTSPRecorderError(Exception):
    """Base exception for RTSP Recorder errors."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> dict:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }


# ===== Configuration Errors =====

class ConfigurationError(RTSPRecorderError):
    """Error in configuration settings."""
    pass


class InvalidConfigError(ConfigurationError):
    """Invalid configuration value provided."""
    
    def __init__(self, key: str, value: Any, reason: str) -> None:
        super().__init__(
            f"Invalid configuration for '{key}': {reason}",
            {"key": key, "value": str(value), "reason": reason}
        )


class MissingConfigError(ConfigurationError):
    """Required configuration is missing."""
    
    def __init__(self, key: str) -> None:
        super().__init__(
            f"Missing required configuration: '{key}'",
            {"key": key}
        )


# ===== Database Errors =====

class DatabaseError(RTSPRecorderError):
    """Database operation failed."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Failed to connect to database."""
    
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(
            f"Failed to connect to database at '{path}': {reason}",
            {"path": path, "reason": reason}
        )


class DatabaseQueryError(DatabaseError):
    """Database query failed."""
    
    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(
            f"Database {operation} failed: {reason}",
            {"operation": operation, "reason": reason}
        )


class MigrationError(DatabaseError):
    """Database migration failed."""
    
    def __init__(self, from_version: int, to_version: int, reason: str) -> None:
        super().__init__(
            f"Migration from v{from_version} to v{to_version} failed: {reason}",
            {"from_version": from_version, "to_version": to_version, "reason": reason}
        )


# ===== Recording Errors =====

class RecordingError(RTSPRecorderError):
    """Recording operation failed."""
    pass


class CameraConnectionError(RecordingError):
    """Failed to connect to camera."""
    
    def __init__(self, camera_name: str, url: str, reason: str) -> None:
        super().__init__(
            f"Failed to connect to camera '{camera_name}': {reason}",
            {"camera": camera_name, "url": url, "reason": reason}
        )


class RecordingStartError(RecordingError):
    """Failed to start recording."""
    
    def __init__(self, camera_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to start recording for '{camera_name}': {reason}",
            {"camera": camera_name, "reason": reason}
        )


class RecordingStopError(RecordingError):
    """Failed to stop recording cleanly."""
    
    def __init__(self, camera_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to stop recording for '{camera_name}': {reason}",
            {"camera": camera_name, "reason": reason}
        )


class StorageError(RecordingError):
    """Storage operation failed."""
    
    def __init__(self, path: str, operation: str, reason: str) -> None:
        super().__init__(
            f"Storage {operation} failed for '{path}': {reason}",
            {"path": path, "operation": operation, "reason": reason}
        )


# ===== Analysis Errors =====

class AnalysisError(RTSPRecorderError):
    """Analysis operation failed."""
    pass


class DetectorError(AnalysisError):
    """Detector service error."""
    
    def __init__(self, url: str, reason: str) -> None:
        super().__init__(
            f"Detector service error at '{url}': {reason}",
            {"url": url, "reason": reason}
        )


class ModelLoadError(AnalysisError):
    """Failed to load ML model."""
    
    def __init__(self, model_name: str, reason: str) -> None:
        super().__init__(
            f"Failed to load model '{model_name}': {reason}",
            {"model": model_name, "reason": reason}
        )


class VideoProcessingError(AnalysisError):
    """Failed to process video file."""
    
    def __init__(self, video_path: str, reason: str) -> None:
        super().__init__(
            f"Failed to process video '{video_path}': {reason}",
            {"video": video_path, "reason": reason}
        )


# ===== Face Recognition Errors =====

class FaceRecognitionError(RTSPRecorderError):
    """Face recognition operation failed."""
    pass


class FaceDetectionError(FaceRecognitionError):
    """Failed to detect face in image."""
    
    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Face detection failed: {reason}",
            {"reason": reason}
        )


class FaceEmbeddingError(FaceRecognitionError):
    """Failed to generate face embedding."""
    
    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Face embedding generation failed: {reason}",
            {"reason": reason}
        )


class FaceMatchError(FaceRecognitionError):
    """Face matching operation failed."""
    
    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Face matching failed: {reason}",
            {"reason": reason}
        )


# ===== Person Database Errors =====

class PersonDatabaseError(RTSPRecorderError):
    """Person database operation failed."""
    pass


class PersonNotFoundError(PersonDatabaseError):
    """Person not found in database."""
    
    def __init__(self, person_id: str) -> None:
        super().__init__(
            f"Person with ID '{person_id}' not found",
            {"person_id": person_id}
        )


class DuplicatePersonError(PersonDatabaseError):
    """Person already exists in database."""
    
    def __init__(self, person_name: str) -> None:
        super().__init__(
            f"Person '{person_name}' already exists",
            {"person_name": person_name}
        )


class InvalidPersonNameError(PersonDatabaseError):
    """Invalid person name provided."""
    
    def __init__(self, name: str, reason: str) -> None:
        super().__init__(
            f"Invalid person name '{name}': {reason}",
            {"name": name, "reason": reason}
        )


# ===== API Errors =====

class APIError(RTSPRecorderError):
    """API operation failed."""
    pass


class RateLimitExceededError(APIError):
    """Rate limit exceeded."""
    
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            f"Rate limit exceeded. Retry after {retry_after} seconds",
            {"retry_after": retry_after}
        )


class AuthenticationError(APIError):
    """Authentication failed."""
    
    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Authentication failed: {reason}",
            {"reason": reason}
        )


class ValidationError(APIError):
    """Input validation failed."""
    
    def __init__(self, field: str, reason: str) -> None:
        super().__init__(
            f"Validation failed for '{field}': {reason}",
            {"field": field, "reason": reason}
        )


# ===== Utility Functions =====

def handle_exception(exc: Exception, context: str = "") -> dict:
    """Convert any exception to a standardized error dict.
    
    Args:
        exc: The exception to handle
        context: Optional context string for logging
        
    Returns:
        Dictionary with error information
    """
    if isinstance(exc, RTSPRecorderError):
        return exc.to_dict()
    
    # Generic exception handling
    return {
        "error": type(exc).__name__,
        "message": str(exc),
        "details": {"context": context} if context else {},
    }


def raise_for_status(response_dict: dict) -> None:
    """Raise exception if response indicates an error.
    
    Args:
        response_dict: Response dictionary to check
        
    Raises:
        RTSPRecorderError: If response contains an error
    """
    if "error" in response_dict:
        raise RTSPRecorderError(
            response_dict.get("message", "Unknown error"),
            response_dict.get("details", {})
        )
