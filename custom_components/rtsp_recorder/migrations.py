"""Database migrations for RTSP Recorder.

This module handles automatic database schema migrations to ensure
backward compatibility when upgrading the integration.

Feature: MED-003 Database Migrations (Audit Report v1.1.0)
"""
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    from .exceptions import MigrationError, DatabaseConnectionError
except ImportError:
    # Fallback for standalone testing
    class MigrationError(Exception):
        def __init__(self, from_ver, to_ver, reason):
            super().__init__(f"Migration {from_ver}→{to_ver} failed: {reason}")
    
    class DatabaseConnectionError(Exception):
        def __init__(self, path, reason):
            super().__init__(f"DB connection to {path} failed: {reason}")

_LOGGER = logging.getLogger(__name__)

# Current schema version
CURRENT_SCHEMA_VERSION = 2


@dataclass
class Migration:
    """Represents a database migration."""
    version: int
    description: str
    up: Callable[[sqlite3.Connection], None]
    down: Callable[[sqlite3.Connection], None] | None = None


def _migration_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migration from v1 to v2: Add movement profile support.
    
    Changes:
    - Add person_entities_enabled column to config
    - Add index on recognition_history for faster queries
    - Add schema_version table
    """
    cursor = conn.cursor()
    
    # Create schema_version table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        )
    """)
    
    # Add index on recognition_history for movement profile queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_recognition_history_time 
        ON recognition_history(recognized_at DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_recognition_history_person 
        ON recognition_history(person_name, recognized_at DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_recognition_history_camera 
        ON recognition_history(camera_name, recognized_at DESC)
    """)
    
    # Record migration
    cursor.execute(
        "INSERT INTO schema_version (version, description) VALUES (?, ?)",
        (2, "Add movement profile indexes")
    )
    
    conn.commit()
    _LOGGER.info("Migration v1→v2 completed: Added movement profile indexes")


def _migration_v2_down(conn: sqlite3.Connection) -> None:
    """Rollback migration v2 to v1."""
    cursor = conn.cursor()
    
    cursor.execute("DROP INDEX IF EXISTS idx_recognition_history_time")
    cursor.execute("DROP INDEX IF EXISTS idx_recognition_history_person")
    cursor.execute("DROP INDEX IF EXISTS idx_recognition_history_camera")
    cursor.execute("DELETE FROM schema_version WHERE version = 2")
    
    conn.commit()
    _LOGGER.info("Migration v2→v1 rollback completed")


# Migration registry
MIGRATIONS: list[Migration] = [
    Migration(
        version=2,
        description="Add movement profile indexes",
        up=_migration_v1_to_v2,
        down=_migration_v2_down,
    ),
]


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get current database schema version.
    
    Args:
        conn: Database connection
        
    Returns:
        Current schema version (0 if no version table)
    """
    try:
        cursor = conn.cursor()
        
        # Check if schema_version table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='schema_version'
        """)
        
        if not cursor.fetchone():
            # No version table = v1 (original schema)
            return 1
        
        # Get highest version
        cursor.execute("SELECT MAX(version) FROM schema_version")
        result = cursor.fetchone()
        
        return result[0] if result[0] else 1
        
    except sqlite3.Error as e:
        _LOGGER.warning(f"Failed to get schema version: {e}")
        return 1


def run_migrations(db_path: str | Path, target_version: int | None = None) -> dict:
    """Run pending database migrations.
    
    Args:
        db_path: Path to database file
        target_version: Target version (None = latest)
        
    Returns:
        Migration result dictionary
    """
    db_path = Path(db_path)
    target = target_version or CURRENT_SCHEMA_VERSION
    
    if not db_path.exists():
        _LOGGER.info(f"Database not found at {db_path}, skipping migrations")
        return {
            "success": True,
            "message": "Database not found, will be created fresh",
            "from_version": 0,
            "to_version": target,
            "migrations_run": [],
        }
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        current = get_current_version(conn)
        
        if current >= target:
            _LOGGER.info(f"Database already at version {current}, no migration needed")
            return {
                "success": True,
                "message": f"Already at version {current}",
                "from_version": current,
                "to_version": current,
                "migrations_run": [],
            }
        
        _LOGGER.info(f"Migrating database from v{current} to v{target}")
        
        migrations_run = []
        
        for migration in MIGRATIONS:
            if migration.version > current and migration.version <= target:
                _LOGGER.info(f"Running migration v{migration.version}: {migration.description}")
                
                try:
                    migration.up(conn)
                    migrations_run.append({
                        "version": migration.version,
                        "description": migration.description,
                        "success": True,
                    })
                except Exception as e:
                    _LOGGER.error(f"Migration v{migration.version} failed: {e}")
                    
                    # Try rollback if available
                    if migration.down:
                        try:
                            migration.down(conn)
                            _LOGGER.info(f"Rolled back migration v{migration.version}")
                        except Exception as rollback_error:
                            _LOGGER.error(f"Rollback failed: {rollback_error}")
                    
                    conn.close()
                    raise MigrationError(current, migration.version, str(e))
        
        conn.close()
        
        final_version = target if migrations_run else current
        
        return {
            "success": True,
            "message": f"Migrated from v{current} to v{final_version}",
            "from_version": current,
            "to_version": final_version,
            "migrations_run": migrations_run,
        }
        
    except sqlite3.Error as e:
        raise DatabaseConnectionError(str(db_path), str(e))


def check_migration_status(db_path: str | Path) -> dict:
    """Check if database needs migration.
    
    Args:
        db_path: Path to database file
        
    Returns:
        Status dictionary
    """
    db_path = Path(db_path)
    
    if not db_path.exists():
        return {
            "needs_migration": False,
            "current_version": 0,
            "target_version": CURRENT_SCHEMA_VERSION,
            "pending_migrations": [],
            "database_exists": False,
        }
    
    try:
        conn = sqlite3.connect(str(db_path))
        current = get_current_version(conn)
        conn.close()
        
        pending = [
            {"version": m.version, "description": m.description}
            for m in MIGRATIONS
            if m.version > current
        ]
        
        return {
            "needs_migration": current < CURRENT_SCHEMA_VERSION,
            "current_version": current,
            "target_version": CURRENT_SCHEMA_VERSION,
            "pending_migrations": pending,
            "database_exists": True,
        }
        
    except sqlite3.Error as e:
        _LOGGER.error(f"Failed to check migration status: {e}")
        return {
            "needs_migration": False,
            "current_version": None,
            "target_version": CURRENT_SCHEMA_VERSION,
            "pending_migrations": [],
            "database_exists": True,
            "error": str(e),
        }


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Initialize database with latest schema.
    
    Called when creating a new database.
    
    Args:
        conn: Database connection
    """
    cursor = conn.cursor()
    
    # Create schema_version table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        )
    """)
    
    # Create all indexes from migrations
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_recognition_history_time 
        ON recognition_history(recognized_at DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_recognition_history_person 
        ON recognition_history(person_name, recognized_at DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_recognition_history_camera 
        ON recognition_history(camera_name, recognized_at DESC)
    """)
    
    # Record current version
    cursor.execute(
        "INSERT OR REPLACE INTO schema_version (version, description) VALUES (?, ?)",
        (CURRENT_SCHEMA_VERSION, "Fresh installation")
    )
    
    conn.commit()
    _LOGGER.info(f"Initialized database schema at version {CURRENT_SCHEMA_VERSION}")
