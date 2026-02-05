"""SQLite Database Manager for RTSP Recorder.

Provides persistent storage for:
- People database (faces, embeddings)
- Recognition history (who was seen when/where)
- Analytics and statistics

Version: 1.0.9
"""

import sqlite3
import json
import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
import threading

_LOGGER = logging.getLogger(__name__)

# Database schema version for migrations
SCHEMA_VERSION = 1

# SQL statements for schema creation
CREATE_SCHEMA = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- People table (known persons)
CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    metadata TEXT  -- JSON for additional data
);

-- Face embeddings table
CREATE TABLE IF NOT EXISTS face_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL,
    embedding BLOB NOT NULL,  -- Stored as binary for efficiency
    source_image TEXT,        -- Path to source image
    created_at TEXT NOT NULL,
    confidence REAL,
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
);

-- Ignored embeddings table (global - not person-specific)
CREATE TABLE IF NOT EXISTS ignored_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    embedding BLOB NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    camera_name TEXT
);

-- Negative embeddings table (person-specific - "NOT this person")
CREATE TABLE IF NOT EXISTS negative_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL,
    embedding BLOB NOT NULL,
    source TEXT,              -- 'manual', 'analysis', etc.
    thumb TEXT,               -- Path to thumbnail image
    created_at TEXT NOT NULL,
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
);

-- Recognition history table (for analytics)
CREATE TABLE IF NOT EXISTS recognition_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT,
    person_name TEXT,
    camera_name TEXT NOT NULL,
    recognized_at TEXT NOT NULL,
    confidence REAL,
    recording_path TEXT,
    frame_path TEXT,
    is_unknown INTEGER DEFAULT 0,
    metadata TEXT,  -- JSON for bbox, landmarks, etc.
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE SET NULL
);

-- Analysis runs table (metadata for each video analysis)
CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_path TEXT NOT NULL,
    analysis_path TEXT,           -- Path to analysis folder
    camera_name TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT DEFAULT 'running', -- 'running', 'completed', 'failed'
    frame_count INTEGER DEFAULT 0,
    frame_interval REAL,
    video_duration REAL,
    video_size_mb REAL,
    device_used TEXT,             -- 'cpu', 'coral_usb'
    processing_time_sec REAL,
    objects_found TEXT,           -- JSON array of unique objects
    persons_detected INTEGER DEFAULT 0,
    faces_detected INTEGER DEFAULT 0,
    faces_matched INTEGER DEFAULT 0,
    error_message TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_recognition_history_person ON recognition_history(person_id);
CREATE INDEX IF NOT EXISTS idx_recognition_history_camera ON recognition_history(camera_name);
CREATE INDEX IF NOT EXISTS idx_recognition_history_time ON recognition_history(recognized_at);
CREATE INDEX IF NOT EXISTS idx_face_embeddings_person ON face_embeddings(person_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_video ON analysis_runs(video_path);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_camera ON analysis_runs(camera_name);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_created ON analysis_runs(created_at);
"""


class DatabaseManager:
    """Thread-safe SQLite database manager for RTSP Recorder."""
    
    def __init__(self, db_path: str) -> None:
        """Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._initialized = False
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable foreign keys
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            # WAL mode for better concurrency
            self._local.connection.execute("PRAGMA journal_mode = WAL")
        return self._local.connection
    
    @property
    def conn(self) -> sqlite3.Connection:
        """Get database connection."""
        return self._get_connection()
    
    def initialize(self) -> bool:
        """Initialize database schema.
        
        Returns:
            True if successful, False otherwise
        """
        if self._initialized:
            return True
            
        try:
            with self._lock:
                cursor = self.conn.cursor()
                
                # Check if schema exists
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
                )
                
                if cursor.fetchone() is None:
                    # Fresh database - create schema
                    _LOGGER.info("Creating new database schema")
                    cursor.executescript(CREATE_SCHEMA)
                    cursor.execute(
                        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                        (SCHEMA_VERSION, datetime.now().isoformat())
                    )
                    self.conn.commit()
                else:
                    # Check schema version and migrate if needed
                    cursor.execute("SELECT MAX(version) FROM schema_version")
                    current_version = cursor.fetchone()[0] or 0
                    
                    if current_version < SCHEMA_VERSION:
                        self._migrate(current_version, SCHEMA_VERSION)
                
                self._initialized = True
                _LOGGER.info(f"Database initialized: {self.db_path}")
                return True
                
        except Exception as e:
            _LOGGER.error(f"Failed to initialize database: {e}")
            return False
    
    def _migrate(self, from_version: int, to_version: int) -> None:
        """Run database migrations.
        
        Args:
            from_version: Current schema version
            to_version: Target schema version
        """
        _LOGGER.info(f"Migrating database from v{from_version} to v{to_version}")
        
        # Add migration logic here for future schema changes
        # Example:
        # if from_version < 2:
        #     self.conn.execute("ALTER TABLE people ADD COLUMN notes TEXT")
        
        self.conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (to_version, datetime.now().isoformat())
        )
        self.conn.commit()
    
    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
    
    # ==================== People Operations ====================
    
    def add_person(self, person_id: str, name: str, metadata: dict = None) -> bool:
        """Add a new person to the database.
        
        Args:
            person_id: Unique identifier
            name: Person's name
            metadata: Optional additional data
            
        Returns:
            True if successful
        """
        try:
            now = datetime.now().isoformat()
            self.conn.execute(
                """INSERT OR REPLACE INTO people 
                   (id, name, created_at, updated_at, is_active, metadata)
                   VALUES (?, ?, ?, ?, 1, ?)""",
                (person_id, name, now, now, json.dumps(metadata or {}))
            )
            self.conn.commit()
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to add person {name}: {e}")
            return False
    
    def get_person(self, person_id: str) -> Optional[Dict]:
        """Get person by ID.
        
        Args:
            person_id: Person's unique identifier
            
        Returns:
            Person dict or None
        """
        cursor = self.conn.execute(
            "SELECT * FROM people WHERE id = ? AND is_active = 1",
            (person_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def get_all_people(self) -> List[Dict]:
        """Get all active people.
        
        Returns:
            List of person dicts
        """
        cursor = self.conn.execute(
            "SELECT * FROM people WHERE is_active = 1 ORDER BY name"
        )
        return [dict(row) for row in cursor.fetchall()]
    
    def update_person(self, person_id: str, name: str = None, metadata: dict = None) -> bool:
        """Update person details.
        
        Args:
            person_id: Person's unique identifier
            name: New name (optional)
            metadata: New metadata (optional)
            
        Returns:
            True if successful
        """
        try:
            now = datetime.now().isoformat()
            if name and metadata is not None:
                self.conn.execute(
                    "UPDATE people SET updated_at = ?, name = ?, metadata = ? WHERE id = ?",
                    (now, name, json.dumps(metadata), person_id)
                )
            elif name:
                self.conn.execute(
                    "UPDATE people SET updated_at = ?, name = ? WHERE id = ?",
                    (now, name, person_id)
                )
            elif metadata is not None:
                self.conn.execute(
                    "UPDATE people SET updated_at = ?, metadata = ? WHERE id = ?",
                    (now, json.dumps(metadata), person_id)
                )
            else:
                self.conn.execute(
                    "UPDATE people SET updated_at = ? WHERE id = ?",
                    (now, person_id)
                )
            self.conn.commit()
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to update person {person_id}: {e}")
            return False
    
    def delete_person(self, person_id: str, hard_delete: bool = False) -> bool:
        """Delete a person (soft delete by default).
        
        Args:
            person_id: Person's unique identifier
            hard_delete: If True, permanently remove
            
        Returns:
            True if successful
        """
        try:
            if hard_delete:
                # First delete all embeddings for this person
                self.conn.execute("DELETE FROM face_embeddings WHERE person_id = ?", (person_id,))
                # Then delete the person
                cursor = self.conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
                self.conn.commit()
                return cursor.rowcount > 0
            else:
                cursor = self.conn.execute(
                    "UPDATE people SET is_active = 0, updated_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), person_id)
                )
                self.conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            _LOGGER.error(f"Failed to delete person {person_id}: {e}")
            return False
    
    # ==================== Embedding Operations ====================
    
    def add_embedding(self, person_id: str, embedding: List[float], 
                     source_image: str = None, confidence: float = None) -> int:
        """Add face embedding for a person.
        
        Args:
            person_id: Person's unique identifier
            embedding: Face embedding vector
            source_image: Path to source image
            confidence: Detection confidence
            
        Returns:
            Embedding ID or -1 on failure
        """
        try:
            # Store embedding as binary blob for efficiency
            embedding_blob = self._embedding_to_blob(embedding)
            
            cursor = self.conn.execute(
                """INSERT INTO face_embeddings 
                   (person_id, embedding, source_image, created_at, confidence)
                   VALUES (?, ?, ?, ?, ?)""",
                (person_id, embedding_blob, source_image, 
                 datetime.now().isoformat(), confidence)
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            _LOGGER.error(f"Failed to add embedding for {person_id}: {e}")
            return -1
    
    def get_embeddings_for_person(self, person_id: str) -> List[List[float]]:
        """Get all embeddings for a person.
        
        Args:
            person_id: Person's unique identifier
            
        Returns:
            List of embedding vectors
        """
        cursor = self.conn.execute(
            "SELECT embedding FROM face_embeddings WHERE person_id = ?",
            (person_id,)
        )
        return [self._blob_to_embedding(row[0]) for row in cursor.fetchall()]
    
    def get_embeddings_with_thumbs_for_person(self, person_id: str) -> List[Dict[str, Any]]:
        """Get all embeddings with thumbnails for a person.
        
        Args:
            person_id: Person's unique identifier
            
        Returns:
            List of dicts with 'vector' and 'thumb' keys
        """
        cursor = self.conn.execute(
            "SELECT embedding, source_image FROM face_embeddings WHERE person_id = ? ORDER BY created_at DESC",
            (person_id,)
        )
        return [
            {"vector": self._blob_to_embedding(row[0]), "thumb": row[1]}
            for row in cursor.fetchall()
        ]
    
    def get_person_details(self, person_id: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive person details including all embeddings with IDs.
        
        Args:
            person_id: Person's unique identifier
            
        Returns:
            Dict with person info, embeddings (positive), negative samples, and stats
        """
        # Get person info
        person = self.get_person(person_id)
        if not person:
            return None
        
        # Get positive embeddings with IDs (source_image is thumbnail)
        cursor = self.conn.execute(
            """SELECT id, source_image, created_at, confidence 
               FROM face_embeddings WHERE person_id = ? ORDER BY created_at DESC""",
            (person_id,)
        )
        positive_samples = []
        for row in cursor.fetchall():
            positive_samples.append({
                "id": row[0],
                "thumb": row[1],
                "created_at": row[2],
                "confidence": row[3],
                "type": "positive"
            })
        
        # Get negative samples for this person
        cursor = self.conn.execute(
            """SELECT id, thumb, created_at 
               FROM negative_embeddings WHERE person_id = ? ORDER BY created_at DESC""",
            (person_id,)
        )
        negative_samples = []
        for row in cursor.fetchall():
            negative_samples.append({
                "id": row[0],
                "thumb": row[1],
                "created_at": row[2],
                "type": "negative"
            })
        
        # Get person name for fallback query
        person_name = person.get("name", "")
        
        # Get recognition count (check both person_id and person_name since older entries may only have name)
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM recognition_history WHERE person_id = ? OR person_name = ?",
            (person_id, person_name)
        )
        recognition_count = cursor.fetchone()[0]
        
        # Get last seen (check both person_id and person_name)
        cursor = self.conn.execute(
            """SELECT camera_name, recognized_at FROM recognition_history 
               WHERE person_id = ? OR person_name = ? ORDER BY recognized_at DESC LIMIT 1""",
            (person_id, person_name)
        )
        last_seen_row = cursor.fetchone()
        last_seen = None
        last_camera = None
        if last_seen_row:
            last_camera = last_seen_row[0]
            last_seen = last_seen_row[1]
        
        return {
            "id": person_id,
            "name": person.get("name", "Unknown"),
            "created_at": person.get("created_at"),
            "positive_samples": positive_samples,
            "negative_samples": negative_samples,
            "positive_count": len(positive_samples),
            "negative_count": len(negative_samples),
            "recognition_count": recognition_count,
            "last_seen": last_seen,
            "last_camera": last_camera
        }
    
    def delete_positive_embedding(self, embedding_id: int) -> bool:
        """Delete a positive embedding by ID.
        
        Args:
            embedding_id: Embedding's unique identifier
            
        Returns:
            True if successful
        """
        return self.delete_embedding(embedding_id)
    
    def delete_negative_embedding(self, embedding_id: int) -> bool:
        """Delete a negative embedding by ID.
        
        Args:
            embedding_id: Negative embedding's unique identifier
            
        Returns:
            True if successful
        """
        try:
            cursor = self.conn.execute(
                "DELETE FROM negative_embeddings WHERE id = ?",
                (embedding_id,)
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            _LOGGER.error(f"Failed to delete negative embedding {embedding_id}: {e}")
            return False
    
    # ==================== Negative Embeddings (Person-specific) ====================
    
    def add_negative_embedding(self, person_id: str, embedding: List[float],
                               source: str = None, thumb: str = None,
                               confidence: float = None) -> int:
        """Add a negative embedding for a person (mark as 'NOT this person').
        
        Args:
            person_id: Person's unique identifier
            embedding: Face embedding vector
            source: Source of the embedding ('manual', 'analysis', etc.)
            thumb: Path to thumbnail/source image
            confidence: Detection confidence
            
        Returns:
            Embedding ID or -1 on failure
        """
        try:
            embedding_blob = self._embedding_to_blob(embedding)
            cursor = self.conn.execute(
                """INSERT INTO negative_embeddings 
                   (person_id, embedding, thumb, created_at, source)
                   VALUES (?, ?, ?, ?, ?)""",
                (person_id, embedding_blob, thumb, 
                 datetime.now().isoformat(), source)
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            _LOGGER.error(f"Failed to add negative embedding for {person_id}: {e}")
            return -1
    
    def get_negative_embeddings_for_person(self, person_id: str) -> List[Dict[str, Any]]:
        """Get all negative embeddings for a person.
        
        Args:
            person_id: Person's unique identifier
            
        Returns:
            List of dicts with 'vector', 'thumb', etc.
        """
        cursor = self.conn.execute(
            """SELECT embedding, thumb, created_at, source
               FROM negative_embeddings WHERE person_id = ? ORDER BY created_at DESC""",
            (person_id,)
        )
        return [
            {
                "vector": self._blob_to_embedding(row[0]),
                "thumb": row[1],
                "created_at": row[2],
                "source": row[3]
            }
            for row in cursor.fetchall()
        ]
    
    def get_negative_count_for_person(self, person_id: str) -> int:
        """Get count of negative embeddings for a person.
        
        Args:
            person_id: Person's unique identifier
            
        Returns:
            Number of negative embeddings
        """
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM negative_embeddings WHERE person_id = ?",
            (person_id,)
        )
        return cursor.fetchone()[0]
    
    def get_all_embeddings(self) -> Dict[str, List[List[float]]]:
        """Get all embeddings grouped by person.
        
        Returns:
            Dict mapping person_id to list of embeddings
        """
        result = {}
        cursor = self.conn.execute(
            """SELECT p.id, p.name, fe.embedding 
               FROM people p 
               JOIN face_embeddings fe ON p.id = fe.person_id
               WHERE p.is_active = 1"""
        )
        for row in cursor.fetchall():
            person_id = row[0]
            if person_id not in result:
                result[person_id] = []
            result[person_id].append(self._blob_to_embedding(row[2]))
        return result
    
    def delete_embedding(self, embedding_id: int) -> bool:
        """Delete a specific embedding.
        
        Args:
            embedding_id: Embedding's unique identifier
            
        Returns:
            True if successful
        """
        try:
            self.conn.execute(
                "DELETE FROM face_embeddings WHERE id = ?",
                (embedding_id,)
            )
            self.conn.commit()
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to delete embedding {embedding_id}: {e}")
            return False
    
    # ==================== Ignored Embeddings ====================
    
    def add_ignored_embedding(self, embedding: List[float], 
                              reason: str = None, camera_name: str = None) -> int:
        """Add embedding to ignore list.
        
        Args:
            embedding: Face embedding vector to ignore
            reason: Why it's being ignored
            camera_name: Camera where it was detected
            
        Returns:
            ID or -1 on failure
        """
        try:
            embedding_blob = self._embedding_to_blob(embedding)
            cursor = self.conn.execute(
                """INSERT INTO ignored_embeddings 
                   (embedding, reason, created_at, camera_name)
                   VALUES (?, ?, ?, ?)""",
                (embedding_blob, reason, datetime.now().isoformat(), camera_name)
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            _LOGGER.error(f"Failed to add ignored embedding: {e}")
            return -1
    
    def get_ignored_embeddings(self) -> List[List[float]]:
        """Get all ignored embeddings.
        
        Returns:
            List of embedding vectors
        """
        cursor = self.conn.execute("SELECT embedding FROM ignored_embeddings")
        return [self._blob_to_embedding(row[0]) for row in cursor.fetchall()]
    
    def clear_ignored_embeddings(self) -> bool:
        """Clear all ignored embeddings.
        
        Returns:
            True if successful
        """
        try:
            self.conn.execute("DELETE FROM ignored_embeddings")
            self.conn.commit()
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to clear ignored embeddings: {e}")
            return False
    
    # ==================== Recognition History ====================
    
    def add_recognition(self, camera_name: str, person_id: str = None,
                       person_name: str = None, confidence: float = None,
                       recording_path: str = None, frame_path: str = None,
                       is_unknown: bool = False, metadata: dict = None) -> int:
        """Log a face recognition event.
        
        Args:
            camera_name: Camera that detected the face
            person_id: Matched person ID (if known)
            person_name: Person name
            confidence: Match confidence
            recording_path: Path to recording
            frame_path: Path to frame image
            is_unknown: True if face not matched
            metadata: Additional data (bbox, landmarks)
            
        Returns:
            History entry ID or -1 on failure
        """
        try:
            cursor = self.conn.execute(
                """INSERT INTO recognition_history 
                   (person_id, person_name, camera_name, recognized_at, 
                    confidence, recording_path, frame_path, is_unknown, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (person_id, person_name, camera_name, datetime.now().isoformat(),
                 confidence, recording_path, frame_path, 1 if is_unknown else 0,
                 json.dumps(metadata or {}))
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            _LOGGER.error(f"Failed to log recognition: {e}")
            return -1
    
    def get_recognition_history(self, person_id: str = None, 
                                camera_name: str = None,
                                since: datetime = None,
                                limit: int = 100) -> List[Dict]:
        """Query recognition history.
        
        Args:
            person_id: Filter by person
            camera_name: Filter by camera
            since: Only events after this time
            limit: Maximum results
            
        Returns:
            List of recognition events
        """
        query = "SELECT * FROM recognition_history WHERE 1=1"
        params = []
        
        if person_id:
            query += " AND person_id = ?"
            params.append(person_id)
        if camera_name:
            query += " AND camera_name = ?"
            params.append(camera_name)
        if since:
            query += " AND recognized_at >= ?"
            params.append(since.isoformat())
        
        query += " ORDER BY recognized_at DESC LIMIT ?"
        params.append(limit)
        
        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_recognition_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get recognition statistics.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Statistics dict
        """
        since = (datetime.now() - timedelta(days=days)).isoformat()
        
        stats = {
            "period_days": days,
            "total_recognitions": 0,
            "known_faces": 0,
            "unknown_faces": 0,
            "by_person": {},
            "by_camera": {},
            "by_hour": {}
        }
        
        # Total counts
        cursor = self.conn.execute(
            """SELECT COUNT(*), SUM(CASE WHEN is_unknown = 0 THEN 1 ELSE 0 END),
                      SUM(CASE WHEN is_unknown = 1 THEN 1 ELSE 0 END)
               FROM recognition_history WHERE recognized_at >= ?""",
            (since,)
        )
        row = cursor.fetchone()
        stats["total_recognitions"] = row[0] or 0
        stats["known_faces"] = row[1] or 0
        stats["unknown_faces"] = row[2] or 0
        
        # By person
        cursor = self.conn.execute(
            """SELECT person_name, COUNT(*) as cnt 
               FROM recognition_history 
               WHERE recognized_at >= ? AND is_unknown = 0
               GROUP BY person_id ORDER BY cnt DESC""",
            (since,)
        )
        for row in cursor.fetchall():
            stats["by_person"][row[0]] = row[1]
        
        # By camera
        cursor = self.conn.execute(
            """SELECT camera_name, COUNT(*) as cnt 
               FROM recognition_history 
               WHERE recognized_at >= ?
               GROUP BY camera_name ORDER BY cnt DESC""",
            (since,)
        )
        for row in cursor.fetchall():
            stats["by_camera"][row[0]] = row[1]
        
        return stats
    
    def cleanup_old_history(self, days: int = 30) -> int:
        """Delete recognition history older than specified days.
        
        Args:
            days: Keep history newer than this
            
        Returns:
            Number of deleted entries
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = self.conn.execute(
            "DELETE FROM recognition_history WHERE recognized_at < ?",
            (cutoff,)
        )
        self.conn.commit()
        deleted = cursor.rowcount
        _LOGGER.info(f"Cleaned up {deleted} old recognition history entries")
        return deleted
    
    # ==================== Migration from JSON ====================
    
    def migrate_from_json(self, json_path: str) -> Tuple[bool, str]:
        """Migrate data from legacy JSON people_db file.
        
        Args:
            json_path: Path to people_db.json
            
        Returns:
            Tuple of (success, message)
        """
        if not os.path.exists(json_path):
            return False, f"JSON file not found: {json_path}"
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            people_count = 0
            embedding_count = 0
            ignored_count = 0
            
            # Migrate people and their embeddings
            # Handle both dict format (v1.0.8+) and legacy list format
            people_data = data.get("people", {})
            if isinstance(people_data, dict) and people_data:
                for person_id, person_data in people_data.items():
                    name = person_data.get("name", person_id)
                    self.add_person(person_id, name)
                    people_count += 1
                    
                    # Migrate embeddings
                    embeddings = person_data.get("embeddings", [])
                    for emb in embeddings:
                        if isinstance(emb, list) and len(emb) > 0:
                            self.add_embedding(person_id, emb)
                            embedding_count += 1
            
            # Migrate ignored embeddings
            if "ignored_embeddings" in data:
                for emb in data["ignored_embeddings"]:
                    if isinstance(emb, list) and len(emb) > 0:
                        self.add_ignored_embedding(emb, reason="Migrated from JSON")
                        ignored_count += 1
            
            msg = f"Migrated {people_count} people, {embedding_count} embeddings, {ignored_count} ignored"
            _LOGGER.info(f"JSON migration complete: {msg}")
            return True, msg
            
        except Exception as e:
            _LOGGER.error(f"JSON migration failed: {e}")
            return False, str(e)
    
    # ==================== Helper Methods ====================
    
    def _embedding_to_blob(self, embedding: List[float]) -> bytes:
        """Convert embedding list to binary blob.
        
        Args:
            embedding: List of floats
            
        Returns:
            Binary representation
        """
        import struct
        return struct.pack(f'{len(embedding)}f', *embedding)
    
    def _blob_to_embedding(self, blob: bytes) -> List[float]:
        """Convert binary blob back to embedding list.
        
        Args:
            blob: Binary data
            
        Returns:
            List of floats
        """
        import struct
        count = len(blob) // 4  # 4 bytes per float
        return list(struct.unpack(f'{count}f', blob))
    
    def vacuum(self) -> None:
        """Optimize database file size."""
        try:
            self.conn.execute("VACUUM")
            _LOGGER.info("Database vacuumed successfully")
        except Exception as e:
            _LOGGER.error(f"Vacuum failed: {e}")
    
    # ==================== Analysis Runs Methods ====================
    
    def create_analysis_run(
        self,
        video_path: str,
        camera_name: str = None,
        frame_interval: float = None,
        video_size_mb: float = None,
        device_used: str = None
    ) -> int:
        """Create a new analysis run entry.
        
        Args:
            video_path: Path to the video being analyzed
            camera_name: Name of the camera
            frame_interval: Seconds between analyzed frames
            video_size_mb: Size of the video file
            device_used: 'cpu' or 'coral_usb'
            
        Returns:
            ID of the created analysis run
        """
        now = datetime.now().isoformat()
        cursor = self.conn.execute(
            """INSERT INTO analysis_runs 
               (video_path, camera_name, created_at, status, frame_interval, video_size_mb, device_used)
               VALUES (?, ?, ?, 'running', ?, ?, ?)""",
            (video_path, camera_name, now, frame_interval, video_size_mb, device_used)
        )
        self.conn.commit()
        run_id = cursor.lastrowid
        _LOGGER.debug(f"Created analysis run {run_id} for {video_path}")
        return run_id
    
    def update_analysis_run(
        self,
        run_id: int,
        analysis_path: str = None,
        status: str = None,
        frame_count: int = None,
        video_duration: float = None,
        processing_time_sec: float = None,
        objects_found: List[str] = None,
        persons_detected: int = None,
        faces_detected: int = None,
        faces_matched: int = None,
        error_message: str = None
    ) -> bool:
        """Update an existing analysis run.
        
        Args:
            run_id: ID of the analysis run
            Various optional fields to update
            
        Returns:
            True if successful
        """
        updates = []
        values = []
        
        if analysis_path is not None:
            updates.append("analysis_path = ?")
            values.append(analysis_path)
        if status is not None:
            updates.append("status = ?")
            values.append(status)
            if status == "completed":
                updates.append("completed_at = ?")
                values.append(datetime.now().isoformat())
        if frame_count is not None:
            updates.append("frame_count = ?")
            values.append(frame_count)
        if video_duration is not None:
            updates.append("video_duration = ?")
            values.append(video_duration)
        if processing_time_sec is not None:
            updates.append("processing_time_sec = ?")
            values.append(processing_time_sec)
        if objects_found is not None:
            updates.append("objects_found = ?")
            values.append(json.dumps(objects_found))
        if persons_detected is not None:
            updates.append("persons_detected = ?")
            values.append(persons_detected)
        if faces_detected is not None:
            updates.append("faces_detected = ?")
            values.append(faces_detected)
        if faces_matched is not None:
            updates.append("faces_matched = ?")
            values.append(faces_matched)
        if error_message is not None:
            updates.append("error_message = ?")
            values.append(error_message)
        
        if not updates:
            return True
        
        values.append(run_id)
        sql = f"UPDATE analysis_runs SET {', '.join(updates)} WHERE id = ?"
        
        try:
            self.conn.execute(sql, values)
            self.conn.commit()
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to update analysis run {run_id}: {e}")
            return False
    
    def get_analysis_run(self, run_id: int) -> Optional[Dict]:
        """Get a specific analysis run by ID.
        
        Args:
            run_id: ID of the analysis run
            
        Returns:
            Dict with analysis run data or None
        """
        cursor = self.conn.execute(
            "SELECT * FROM analysis_runs WHERE id = ?", (run_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def get_analysis_runs(
        self,
        camera_name: str = None,
        status: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """Get analysis runs with optional filters.
        
        Args:
            camera_name: Filter by camera
            status: Filter by status
            limit: Max results
            offset: Pagination offset
            
        Returns:
            List of analysis run dicts
        """
        sql = "SELECT * FROM analysis_runs WHERE 1=1"
        params = []
        
        if camera_name:
            sql += " AND camera_name = ?"
            params.append(camera_name)
        if status:
            sql += " AND status = ?"
            params.append(status)
        
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_analysis_stats(self, days: int = 30) -> Dict:
        """Get analysis statistics for the last N days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Dict with statistics
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        stats = {}
        
        # Total runs
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM analysis_runs WHERE created_at > ?", (cutoff,)
        )
        stats["total_runs"] = cursor.fetchone()[0]
        
        # Completed runs
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM analysis_runs WHERE created_at > ? AND status = 'completed'",
            (cutoff,)
        )
        stats["completed_runs"] = cursor.fetchone()[0]
        
        # Total faces detected
        cursor = self.conn.execute(
            "SELECT SUM(faces_detected) FROM analysis_runs WHERE created_at > ?",
            (cutoff,)
        )
        result = cursor.fetchone()[0]
        stats["total_faces_detected"] = result or 0
        
        # Total faces matched
        cursor = self.conn.execute(
            "SELECT SUM(faces_matched) FROM analysis_runs WHERE created_at > ?",
            (cutoff,)
        )
        result = cursor.fetchone()[0]
        stats["total_faces_matched"] = result or 0
        
        # Average processing time
        cursor = self.conn.execute(
            "SELECT AVG(processing_time_sec) FROM analysis_runs WHERE created_at > ? AND status = 'completed'",
            (cutoff,)
        )
        result = cursor.fetchone()[0]
        stats["avg_processing_time_sec"] = round(result, 2) if result else 0
        
        return stats
    
    def delete_analysis_run(self, run_id: int) -> bool:
        """Delete an analysis run.
        
        Args:
            run_id: ID of the analysis run
            
        Returns:
            True if deleted
        """
        try:
            self.conn.execute("DELETE FROM analysis_runs WHERE id = ?", (run_id,))
            self.conn.commit()
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to delete analysis run {run_id}: {e}")
            return False
    
    def cleanup_old_analysis_runs(self, days: int = 90) -> int:
        """Delete analysis runs older than N days.
        
        Args:
            days: Delete runs older than this
            
        Returns:
            Number of deleted runs
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = self.conn.execute(
            "DELETE FROM analysis_runs WHERE created_at < ?", (cutoff,)
        )
        self.conn.commit()
        deleted = cursor.rowcount
        if deleted:
            _LOGGER.info(f"Cleaned up {deleted} old analysis runs")
        return deleted

    def get_db_stats(self) -> Dict[str, int]:
        """Get database statistics.
        
        Returns:
            Dict with counts
        """
        stats = {}
        
        cursor = self.conn.execute("SELECT COUNT(*) FROM people WHERE is_active = 1")
        stats["people"] = cursor.fetchone()[0]
        
        cursor = self.conn.execute("SELECT COUNT(*) FROM face_embeddings")
        stats["embeddings"] = cursor.fetchone()[0]
        
        cursor = self.conn.execute("SELECT COUNT(*) FROM ignored_embeddings")
        stats["ignored"] = cursor.fetchone()[0]
        
        cursor = self.conn.execute("SELECT COUNT(*) FROM recognition_history")
        stats["history"] = cursor.fetchone()[0]
        
        # Analysis runs count
        try:
            cursor = self.conn.execute("SELECT COUNT(*) FROM analysis_runs")
            stats["analysis_runs"] = cursor.fetchone()[0]
        except:
            stats["analysis_runs"] = 0
        
        # Database file size
        if os.path.exists(self.db_path):
            stats["db_size_mb"] = round(os.path.getsize(self.db_path) / 1024 / 1024, 2)
        
        return stats


# Singleton instance for the integration
_db_instance: Optional[DatabaseManager] = None


def get_database(hass_config_path: str = None) -> DatabaseManager:
    """Get or create database instance.
    
    Args:
        hass_config_path: Home Assistant config path
        
    Returns:
        DatabaseManager instance
    """
    global _db_instance
    
    if _db_instance is None:
        if hass_config_path is None:
            hass_config_path = "/config"
        
        db_path = os.path.join(hass_config_path, "rtsp_recorder", "rtsp_recorder.db")
        _db_instance = DatabaseManager(db_path)
        _db_instance.initialize()
    
    return _db_instance


def close_database() -> None:
    """Close database connection."""
    global _db_instance
    if _db_instance:
        _db_instance.close()
        _db_instance = None
