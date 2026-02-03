"""Unit tests for Migrations module.

Feature: MED-001 Unit Test Framework (Audit Report v1.1.0)
"""
import sqlite3
import pytest
import sys
from pathlib import Path

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rtsp_recorder"))

try:
    from migrations import (
        CURRENT_SCHEMA_VERSION,
        get_current_version,
        run_migrations,
        check_migration_status,
        initialize_schema,
    )
except ImportError:
    CURRENT_SCHEMA_VERSION = None


@pytest.mark.unit
class TestGetCurrentVersion:
    """Tests for get_current_version function."""
    
    def test_new_database_returns_version_1(self, tmp_path):
        """Test that new database without version table returns 1."""
        if CURRENT_SCHEMA_VERSION is None:
            pytest.skip("Module not available")
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        # Create a table but no schema_version
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        
        version = get_current_version(conn)
        
        assert version == 1
        conn.close()
    
    def test_database_with_version_table(self, tmp_path):
        """Test database with existing version table."""
        if CURRENT_SCHEMA_VERSION is None:
            pytest.skip("Module not available")
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        # Create schema_version table with version 2
        conn.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP,
                description TEXT
            )
        """)
        conn.execute("INSERT INTO schema_version (version, description) VALUES (2, 'Test')")
        conn.commit()
        
        version = get_current_version(conn)
        
        assert version == 2
        conn.close()


@pytest.mark.unit
class TestCheckMigrationStatus:
    """Tests for check_migration_status function."""
    
    def test_nonexistent_database(self, tmp_path):
        """Test status check for non-existent database."""
        if CURRENT_SCHEMA_VERSION is None:
            pytest.skip("Module not available")
        
        db_path = tmp_path / "nonexistent.db"
        
        status = check_migration_status(db_path)
        
        assert status["needs_migration"] is False
        assert status["database_exists"] is False
        assert status["current_version"] == 0
    
    def test_database_at_current_version(self, tmp_path):
        """Test database already at current version."""
        if CURRENT_SCHEMA_VERSION is None:
            pytest.skip("Module not available")
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        # Create schema_version at current version
        conn.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP,
                description TEXT
            )
        """)
        conn.execute(
            "INSERT INTO schema_version (version, description) VALUES (?, ?)",
            (CURRENT_SCHEMA_VERSION, "Current")
        )
        conn.commit()
        conn.close()
        
        status = check_migration_status(db_path)
        
        assert status["needs_migration"] is False
        assert status["database_exists"] is True
        assert status["current_version"] == CURRENT_SCHEMA_VERSION
    
    def test_database_needs_migration(self, tmp_path):
        """Test database that needs migration."""
        if CURRENT_SCHEMA_VERSION is None:
            pytest.skip("Module not available")
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        # Create old database without version table
        conn.execute("CREATE TABLE cameras (id TEXT)")
        conn.commit()
        conn.close()
        
        status = check_migration_status(db_path)
        
        # Version 1 database needs migration to v2
        if CURRENT_SCHEMA_VERSION > 1:
            assert status["needs_migration"] is True
            assert status["current_version"] == 1
            assert len(status["pending_migrations"]) > 0


@pytest.mark.unit
class TestRunMigrations:
    """Tests for run_migrations function."""
    
    def test_migrate_nonexistent_database(self, tmp_path):
        """Test migration on non-existent database."""
        if CURRENT_SCHEMA_VERSION is None:
            pytest.skip("Module not available")
        
        db_path = tmp_path / "new.db"
        
        result = run_migrations(db_path)
        
        assert result["success"] is True
        assert "not found" in result["message"].lower() or result["from_version"] == 0
    
    def test_migrate_from_v1(self, tmp_path):
        """Test migration from version 1."""
        if CURRENT_SCHEMA_VERSION is None:
            pytest.skip("Module not available")
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        # Create v1 schema (no schema_version table)
        conn.execute("""
            CREATE TABLE recognition_history (
                id INTEGER PRIMARY KEY,
                person_name TEXT,
                camera_name TEXT,
                recognized_at TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        
        result = run_migrations(db_path)
        
        assert result["success"] is True
        assert result["from_version"] == 1
        
        if CURRENT_SCHEMA_VERSION > 1:
            assert result["to_version"] >= 2
            assert len(result["migrations_run"]) > 0
    
    def test_already_at_target_version(self, tmp_path):
        """Test when database is already at target version."""
        if CURRENT_SCHEMA_VERSION is None:
            pytest.skip("Module not available")
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        # Create database at current version
        conn.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP,
                description TEXT
            )
        """)
        conn.execute(
            "INSERT INTO schema_version (version, description) VALUES (?, ?)",
            (CURRENT_SCHEMA_VERSION, "Current")
        )
        conn.commit()
        conn.close()
        
        result = run_migrations(db_path)
        
        assert result["success"] is True
        assert result["from_version"] == CURRENT_SCHEMA_VERSION
        assert result["to_version"] == CURRENT_SCHEMA_VERSION
        assert len(result["migrations_run"]) == 0


@pytest.mark.unit
class TestInitializeSchema:
    """Tests for initialize_schema function."""
    
    def test_creates_version_table(self, tmp_path):
        """Test that initialize_schema creates version table."""
        if CURRENT_SCHEMA_VERSION is None:
            pytest.skip("Module not available")
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        # Create required base tables first
        conn.execute("""
            CREATE TABLE recognition_history (
                id INTEGER PRIMARY KEY,
                person_name TEXT,
                camera_name TEXT,
                recognized_at TIMESTAMP
            )
        """)
        
        initialize_schema(conn)
        
        # Check version table exists
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='schema_version'
        """)
        assert cursor.fetchone() is not None
        
        # Check version is set
        cursor = conn.execute("SELECT MAX(version) FROM schema_version")
        version = cursor.fetchone()[0]
        assert version == CURRENT_SCHEMA_VERSION
        
        conn.close()
    
    def test_creates_indexes(self, tmp_path):
        """Test that initialize_schema creates performance indexes."""
        if CURRENT_SCHEMA_VERSION is None:
            pytest.skip("Module not available")
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        
        # Create required base table
        conn.execute("""
            CREATE TABLE recognition_history (
                id INTEGER PRIMARY KEY,
                person_name TEXT,
                camera_name TEXT,
                recognized_at TIMESTAMP
            )
        """)
        
        initialize_schema(conn)
        
        # Check indexes exist
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name LIKE 'idx_recognition_history%'
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        
        assert len(indexes) >= 1  # At least one index should exist
        
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
