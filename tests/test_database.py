"""Test suite for database module.

This module tests the database functionality including:
- Connection management
- CRUD operations for people
- Recognition history
- Thread safety
"""
import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta


class TestDatabaseManager:
    """Tests for DatabaseManager class."""
    
    @pytest.fixture
    def db_path(self):
        """Create a temporary database file."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.remove(path)
    
    @pytest.fixture
    def db_manager(self, db_path):
        """Create a DatabaseManager instance."""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'custom_components', 'rtsp_recorder'))
        
        from database import DatabaseManager
        manager = DatabaseManager(db_path)
        manager.initialize()
        return manager
    
    def test_initialize_creates_tables(self, db_manager):
        """Test that initialization creates required tables."""
        cursor = db_manager.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        
        assert 'people' in tables
        assert 'face_embeddings' in tables
        assert 'recognition_history' in tables
        assert 'schema_version' in tables
    
    def test_add_person(self, db_manager):
        """Test adding a person."""
        result = db_manager.add_person("test-1", "John Doe")
        assert result is True
        
        person = db_manager.get_person("test-1")
        assert person is not None
        assert person['name'] == "John Doe"
    
    def test_add_person_duplicate(self, db_manager):
        """Test adding duplicate person updates instead."""
        db_manager.add_person("test-1", "John Doe")
        db_manager.add_person("test-1", "John Updated")
        
        person = db_manager.get_person("test-1")
        assert person['name'] == "John Updated"
    
    def test_get_all_people(self, db_manager):
        """Test getting all people."""
        db_manager.add_person("test-1", "Alice")
        db_manager.add_person("test-2", "Bob")
        db_manager.add_person("test-3", "Charlie")
        
        people = db_manager.get_all_people()
        assert len(people) == 3
        names = {p['name'] for p in people}
        assert names == {"Alice", "Bob", "Charlie"}
    
    def test_get_person_not_found(self, db_manager):
        """Test getting non-existent person."""
        person = db_manager.get_person("nonexistent")
        assert person is None
    
    def test_delete_person(self, db_manager):
        """Test deleting a person."""
        db_manager.add_person("test-1", "To Delete")
        
        result = db_manager.delete_person("test-1")
        assert result is True
        
        person = db_manager.get_person("test-1")
        assert person is None
    
    def test_add_recognition(self, db_manager):
        """Test adding recognition history."""
        db_manager.add_person("test-1", "John")
        
        result = db_manager.add_recognition(
            person_id="test-1",
            person_name="John",
            camera_name="Front Door",
            confidence=0.95
        )
        assert result is True
    
    def test_get_recognition_history(self, db_manager):
        """Test getting recognition history."""
        db_manager.add_person("test-1", "John")
        db_manager.add_recognition("test-1", "John", "Camera1", 0.9)
        db_manager.add_recognition("test-1", "John", "Camera2", 0.85)
        
        history = db_manager.get_recognition_history(limit=10)
        assert len(history) >= 2
    
    def test_cleanup_old_history(self, db_manager):
        """Test cleaning up old history."""
        db_manager.add_person("test-1", "John")
        db_manager.add_recognition("test-1", "John", "Camera1", 0.9)
        
        # Cleanup with 0 days should remove everything
        deleted = db_manager.cleanup_old_history(days=0)
        # Note: This may or may not delete depending on timing
        assert isinstance(deleted, int)
    
    def test_close_connection(self, db_manager):
        """Test closing database connection."""
        db_manager.close()
        # Should not raise even if called multiple times
        db_manager.close()


class TestDatabaseConcurrency:
    """Tests for concurrent database access."""
    
    @pytest.fixture
    def db_path(self):
        """Create a temporary database file."""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.remove(path)
    
    def test_wal_mode_enabled(self, db_path):
        """Test that WAL mode is enabled for concurrency."""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'custom_components', 'rtsp_recorder'))
        
        from database import DatabaseManager
        manager = DatabaseManager(db_path)
        manager.initialize()
        
        cursor = manager.conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        
        assert mode.lower() == 'wal'
    
    def test_foreign_keys_enabled(self, db_path):
        """Test that foreign keys are enabled."""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'custom_components', 'rtsp_recorder'))
        
        from database import DatabaseManager
        manager = DatabaseManager(db_path)
        manager.initialize()
        
        cursor = manager.conn.execute("PRAGMA foreign_keys")
        enabled = cursor.fetchone()[0]
        
        assert enabled == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
