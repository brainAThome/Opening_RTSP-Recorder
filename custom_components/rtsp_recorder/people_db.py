"""People Database management for RTSP Recorder Integration.

This module handles all CRUD operations for the people database:
- Loading and saving the database file
- Atomic updates with proper locking
- Converting internal data to public view format
- In-memory caching for faster repeated reads
- SQLite backend support for improved performance (v1.0.9+)

Performance optimizations:
- Cached reads avoid disk I/O when data hasn't changed
- Lock-protected atomic operations prevent race conditions
- SQLite with WAL mode for concurrent read/write operations
- Binary embedding storage for reduced database size

Version: 1.0.9 - Added SQLite backend support
"""
import asyncio
import datetime
import json
import os
import logging
from typing import Any, Callable, Optional

from .const import PEOPLE_DB_VERSION
from .face_matching import _update_person_centroid

_LOGGER = logging.getLogger(__name__)

# SQLite backend flag - can be enabled via config
_USE_SQLITE_BACKEND = False
_sqlite_db = None


# Global lock for all database operations
_people_lock = asyncio.Lock()

# ===== In-Memory Cache for People DB =====
# Avoids repeated disk reads when data hasn't changed
_people_cache: dict[str, Any] | None = None
_people_cache_path: str | None = None
_people_cache_mtime: float = 0.0


def _invalidate_cache() -> None:
    """Invalidate the in-memory cache (call after any write)."""
    global _people_cache, _people_cache_mtime
    _people_cache = None
    _people_cache_mtime = 0.0


def _get_cached_or_load(path: str) -> dict[str, Any] | None:
    """Get data from cache if valid, otherwise return None.
    
    Checks file modification time to detect external changes.
    """
    global _people_cache, _people_cache_path, _people_cache_mtime
    
    if _people_cache is None or _people_cache_path != path:
        return None
    
    try:
        current_mtime = os.path.getmtime(path)
        if current_mtime > _people_cache_mtime:
            # File was modified externally, invalidate cache
            _invalidate_cache()
            return None
    except OSError:
        return None
    
    return _people_cache


def _update_cache(path: str, data: dict[str, Any]) -> None:
    """Update the in-memory cache with fresh data."""
    global _people_cache, _people_cache_path, _people_cache_mtime
    
    try:
        _people_cache = data
        _people_cache_path = path
        _people_cache_mtime = os.path.getmtime(path)
    except OSError:
        _people_cache_mtime = 0.0


def _default_people_db() -> dict[str, Any]:
    """Create a new empty people database structure.
    
    Returns:
        Empty people database dict with version and timestamps
    """
    # MED-005 Fix: Use timezone-aware datetime instead of deprecated utcnow()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    return {
        "version": PEOPLE_DB_VERSION,
        "people": [],
        "ignored_embeddings": [],  # Embeddings marked as "skip/ignore"
        "created_utc": now_utc.strftime("%Y%m%d_%H%M%S"),
        "updated_utc": now_utc.strftime("%Y%m%d_%H%M%S"),
    }


async def _load_people_db(path: str, use_cache: bool = True) -> dict[str, Any]:
    """Load people database from JSON file.
    
    Creates a new database file if it doesn't exist.
    Automatically computes missing centroids.
    Uses in-memory cache for faster repeated reads.
    
    Args:
        path: Path to people database JSON file
        use_cache: Whether to use cached data if available (default True)
        
    Returns:
        People database dict (deep copy to prevent accidental modification)
    """
    async with _people_lock:
        # Try cache first
        if use_cache:
            cached = _get_cached_or_load(path)
            if cached is not None:
                # Return deep copy to prevent accidental cache modification
                import copy
                return copy.deepcopy(cached)
        
        if not os.path.exists(path):
            data = _default_people_db()
            def _write():
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            await asyncio.to_thread(_write)
            _update_cache(path, data)
            return data
        try:
            def _read():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            data = await asyncio.to_thread(_read)
            if not isinstance(data, dict):
                return _default_people_db()
            if "people" not in data:
                data["people"] = []
            
            # Ensure centroids are computed for all people
            needs_save = False
            for person in data.get("people", []):
                if "centroid" not in person and person.get("embeddings"):
                    _update_person_centroid(person)
                    needs_save = True
            
            # Save updated centroids if any were computed
            if needs_save:
                data["updated_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
                def _write_updated():
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                await asyncio.to_thread(_write_updated)
            
            # Update cache
            _update_cache(path, data)
            
            # Return copy to prevent cache modification
            import copy
            return copy.deepcopy(data)
        except Exception:
            return _default_people_db()


async def _save_people_db(path: str, data: dict[str, Any]) -> None:
    """Save people database to JSON file.
    
    Creates a backup before writing (MED-001 Fix).
    Invalidates cache after write to ensure consistency.
    
    Args:
        path: Path to people database JSON file
        data: People database dict to save
    """
    async with _people_lock:
        # MED-001 Fix: Create backup before writing
        backup_path = path + ".bak"
        def _create_backup():
            if os.path.exists(path):
                try:
                    import shutil
                    shutil.copy2(path, backup_path)
                except Exception:
                    pass  # Backup failure should not block save
        await asyncio.to_thread(_create_backup)
        
        # MED-005 Fix: Use timezone-aware datetime
        data["updated_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        def _write():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        await asyncio.to_thread(_write)
        
        # Update cache with fresh data
        _update_cache(path, data)


async def _update_people_db(path: str, update_fn: Callable[[dict], dict]) -> dict[str, Any]:
    """Atomically update People DB with a modifier function.
    
    Ensures the entire read-modify-write cycle is protected by a single lock
    to prevent race conditions between concurrent updates.
    
    Args:
        path: Path to people DB JSON file
        update_fn: Function that takes the current data dict and returns modified data
    
    Returns:
        The updated data dict
    """
    async with _people_lock:
        # Read current data
        if not os.path.exists(path):
            data = _default_people_db()
        else:
            try:
                def _read():
                    with open(path, "r", encoding="utf-8") as f:
                        return json.load(f)
                data = await asyncio.to_thread(_read)
                if not isinstance(data, dict):
                    data = _default_people_db()
                if "people" not in data:
                    data["people"] = []
            except Exception:
                data = _default_people_db()
        
        # Apply update function
        data = update_fn(data)
        
        # Save updated data (MED-005 Fix: timezone-aware)
        data["updated_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        def _write():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        await asyncio.to_thread(_write)
        
        return data


def _public_people_view(people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert internal people data to public view format.
    
    Strips embeddings and other internal data, keeping only what the UI needs.
    
    Args:
        people: List of person dicts from internal database
        
    Returns:
        List of person dicts with only public fields
    """
    out = []
    for p in people:
        thumbs = []
        try:
            for emb in (p.get("embeddings") or [])[-5:]:
                if isinstance(emb, dict):
                    t = emb.get("thumb")
                    if t:
                        thumbs.append(t)
        except Exception:
            thumbs = []
        
        # Include negative sample count for UI
        neg_count = len(p.get("negative_embeddings", []) or [])
        
        out.append({
            "id": str(p.get("id")) if p.get("id") is not None else None,
            "name": p.get("name"),
            "created_utc": p.get("created_utc"),
            "embeddings_count": len(p.get("embeddings", []) or []),
            "negative_count": neg_count,
            "recent_thumbs": thumbs,
        })
    return out


def get_people_lock() -> asyncio.Lock:
    """Get the global people database lock.
    
    Use this when you need to perform multiple database operations atomically
    outside of the provided helper functions.
    
    Returns:
        The global asyncio.Lock for people database
    """
    return _people_lock


async def add_ignored_embedding(path: str, embedding: list[float], thumb: str | None = None) -> bool:
    """Add an embedding to the ignored list.
    
    Ignored embeddings are skipped during face matching - useful for
    false positives, background faces, or faces the user doesn't want to track.
    
    Args:
        path: Path to people database JSON file
        embedding: Face embedding vector to ignore
        thumb: Optional thumbnail URL for reference
        
    Returns:
        True if successfully added
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    def update_fn(data: dict[str, Any]) -> dict[str, Any]:
        if "ignored_embeddings" not in data:
            data["ignored_embeddings"] = []
        
        data["ignored_embeddings"].append({
            "embedding": embedding,
            "thumb": thumb,
            "added_utc": now_utc.strftime("%Y%m%d_%H%M%S"),
        })
        data["updated_utc"] = now_utc.strftime("%Y%m%d_%H%M%S")
        return data
    
    await _update_people_db(path, update_fn)
    return True


async def get_ignored_embeddings(path: str) -> list[list[float]]:
    """Get all ignored embeddings.
    
    Args:
        path: Path to people database JSON file
        
    Returns:
        List of embedding vectors that should be ignored
    """
    data = await _load_people_db(path)
    ignored = data.get("ignored_embeddings", [])
    return [item.get("embedding") for item in ignored if item.get("embedding")]


async def get_ignored_count(path: str) -> int:
    """Get count of ignored embeddings.
    
    Args:
        path: Path to people database JSON file
        
    Returns:
        Number of ignored embeddings
    """
    data = await _load_people_db(path)
    return len(data.get("ignored_embeddings", []))


# ==================== SQLite Backend Functions ====================

def enable_sqlite_backend(config_path: str = "/config") -> bool:
    """Enable SQLite backend for improved performance.
    
    This will:
    - Initialize the SQLite database
    - Optionally migrate existing JSON data
    - Enable SQLite for all future operations
    
    Args:
        config_path: Home Assistant config path
        
    Returns:
        True if successfully enabled
    """
    global _USE_SQLITE_BACKEND, _sqlite_db
    
    try:
        from .database import get_database
        
        _sqlite_db = get_database(config_path)
        if _sqlite_db.initialize():
            _USE_SQLITE_BACKEND = True
            _LOGGER.info("SQLite backend enabled for people database")
            return True
        else:
            _LOGGER.error("Failed to initialize SQLite database")
            return False
    except ImportError as e:
        _LOGGER.error(f"SQLite database module not available: {e}")
        return False
    except Exception as e:
        _LOGGER.error(f"Failed to enable SQLite backend: {e}")
        return False


def disable_sqlite_backend() -> None:
    """Disable SQLite backend and use JSON files."""
    global _USE_SQLITE_BACKEND, _sqlite_db
    
    if _sqlite_db:
        from .database import close_database
        close_database()
    
    _USE_SQLITE_BACKEND = False
    _sqlite_db = None
    _LOGGER.info("SQLite backend disabled, using JSON files")


def is_sqlite_enabled() -> bool:
    """Check if SQLite backend is enabled.
    
    Returns:
        True if SQLite is active
    """
    return _USE_SQLITE_BACKEND and _sqlite_db is not None


async def migrate_json_to_sqlite(json_path: str) -> tuple[bool, str]:
    """Migrate existing JSON people database to SQLite.
    
    This should be called once when enabling SQLite for the first time.
    The original JSON file is preserved as a backup.
    
    Args:
        json_path: Path to people_db.json file
        
    Returns:
        Tuple of (success, message)
    """
    if not _sqlite_db:
        return False, "SQLite backend not enabled"
    
    if not os.path.exists(json_path):
        return True, "No JSON file to migrate"
    
    try:
        result = _sqlite_db.migrate_from_json(json_path)
        if result[0]:
            # Rename JSON file to indicate migration complete
            backup_path = json_path + ".migrated"
            os.rename(json_path, backup_path)
            _LOGGER.info(f"JSON migrated to SQLite, backup at {backup_path}")
        return result
    except Exception as e:
        return False, f"Migration failed: {e}"


async def log_recognition_event(
    camera_name: str,
    person_id: str = None,
    person_name: str = None,
    confidence: float = None,
    recording_path: str = None,
    frame_path: str = None,
    is_unknown: bool = False,
    metadata: dict = None
) -> int:
    """Log a face recognition event to the database.
    
    Only works when SQLite backend is enabled.
    Used for analytics and history tracking.
    
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
        History entry ID or -1 if not using SQLite
    """
    if not is_sqlite_enabled():
        return -1
    
    return _sqlite_db.add_recognition(
        camera_name=camera_name,
        person_id=person_id,
        person_name=person_name,
        confidence=confidence,
        recording_path=recording_path,
        frame_path=frame_path,
        is_unknown=is_unknown,
        metadata=metadata
    )


async def get_recognition_stats(days: int = 7) -> dict:
    """Get face recognition statistics.
    
    Only works when SQLite backend is enabled.
    
    Args:
        days: Number of days to analyze
        
    Returns:
        Statistics dict or empty dict if not using SQLite
    """
    if not is_sqlite_enabled():
        return {}
    
    return _sqlite_db.get_recognition_stats(days)


async def get_database_stats() -> dict:
    """Get database statistics.
    
    Returns stats from SQLite if enabled, otherwise from JSON.
    
    Returns:
        Dict with counts and sizes
    """
    if is_sqlite_enabled():
        return _sqlite_db.get_db_stats()
    
    # Fallback to JSON stats
    return {
        "backend": "json",
        "sqlite_available": False
    }
