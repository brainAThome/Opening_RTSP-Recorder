"""People Database management for RTSP Recorder Integration.

This module handles all CRUD operations for the people database using SQLite.
v1.1.0k: SQLite-only - all JSON and path parameters removed.

Features:
- SQLite with WAL mode for concurrent read/write operations
- Binary embedding storage for reduced database size
- Recognition history for movement profiles

Version: 1.1.0k - SQLite-only (cleaned API)
"""
import asyncio
import datetime
import logging
from typing import Any, Optional

from .const import PEOPLE_DB_VERSION

_LOGGER = logging.getLogger(__name__)

# SQLite database instance
_sqlite_db = None

# Global lock for database operations
_people_lock = asyncio.Lock()


def _default_people_db() -> dict[str, Any]:
    """Create a new empty people database structure.
    
    Returns:
        Empty people database dict with version and timestamps
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    return {
        "version": PEOPLE_DB_VERSION,
        "people": [],
        "ignored_embeddings": [],
        "created_utc": now_utc.strftime("%Y%m%d_%H%M%S"),
        "updated_utc": now_utc.strftime("%Y%m%d_%H%M%S"),
    }


async def _load_people_db(use_cache: bool = True) -> dict[str, Any]:
    """Load people database from SQLite.
    
    Args:
        use_cache: Ignored (kept for API compatibility)
        
    Returns:
        People database dict
    """
    async with _people_lock:
        if not _sqlite_db:
            _LOGGER.warning("SQLite database not initialized")
            return _default_people_db()
        
        return await _load_people_from_sqlite()


async def _load_people_from_sqlite() -> dict[str, Any]:
    """Load people from SQLite database.
    
    Converts SQLite format to the dict format expected by the rest of the code.
    
    Returns:
        People database dict
    """
    if not _sqlite_db:
        return _default_people_db()
    
    try:
        people_list = []
        sqlite_people = _sqlite_db.get_all_people()
        
        for p in sqlite_people:
            person_id = p.get("id")
            
            # Get embeddings with thumbnails
            if hasattr(_sqlite_db, 'get_embeddings_with_thumbs_for_person'):
                embeddings = _sqlite_db.get_embeddings_with_thumbs_for_person(person_id)
            else:
                embeddings_raw = _sqlite_db.get_embeddings_for_person(person_id)
                embeddings = [{"vector": emb_vector, "thumb": None} for emb_vector in embeddings_raw]
            
            # Get negative embeddings
            negative_embeddings = []
            if hasattr(_sqlite_db, 'get_negative_embeddings_for_person'):
                negative_embeddings = _sqlite_db.get_negative_embeddings_for_person(person_id)
            
            people_list.append({
                "id": person_id,
                "name": p.get("name"),
                "created_utc": p.get("created_at", ""),
                "embeddings": embeddings,
                "negative_embeddings": negative_embeddings,
                "centroid": None,
            })
        
        # Get ignored embeddings
        raw_ignored = _sqlite_db.get_ignored_embeddings() if hasattr(_sqlite_db, 'get_ignored_embeddings') else []
        ignored = [{"embedding": emb} for emb in raw_ignored if emb]
        
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        return {
            "version": PEOPLE_DB_VERSION,
            "people": people_list,
            "ignored_embeddings": ignored,
            "created_utc": now_utc.strftime("%Y%m%d_%H%M%S"),
            "updated_utc": now_utc.strftime("%Y%m%d_%H%M%S"),
        }
    except Exception as e:
        _LOGGER.error(f"Failed to load people from SQLite: {e}")
        return _default_people_db()


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
    
    Returns:
        The global asyncio.Lock for people database
    """
    return _people_lock


async def add_ignored_embedding(embedding: list[float], thumb: str | None = None) -> bool:
    """Add an embedding to the ignored list.
    
    Args:
        embedding: Face embedding vector to ignore
        thumb: Optional thumbnail URL for reference
        
    Returns:
        True if successfully added
    """
    if not _sqlite_db:
        _LOGGER.error("SQLite database not initialized")
        return False
    
    try:
        result = _sqlite_db.add_ignored_embedding(embedding, reason="User ignored")
        return result > 0
    except Exception as e:
        _LOGGER.error(f"Failed to add ignored embedding: {e}")
        return False


async def get_ignored_embeddings() -> list[list[float]]:
    """Get all ignored embeddings.
    
    Returns:
        List of embedding vectors that should be ignored
    """
    if not _sqlite_db:
        return []
    
    try:
        return _sqlite_db.get_ignored_embeddings()
    except Exception as e:
        _LOGGER.error(f"Failed to get ignored embeddings: {e}")
        return []


async def get_ignored_count() -> int:
    """Get count of ignored embeddings.
    
    Returns:
        Number of ignored embeddings
    """
    if not _sqlite_db:
        return 0
    
    try:
        return len(_sqlite_db.get_ignored_embeddings())
    except Exception:
        return 0


# ==================== SQLite Functions ====================

async def _save_person_to_sqlite(person_id: str, name: str, embeddings: list = None) -> bool:
    """Save a person to SQLite database.
    
    Args:
        person_id: Unique person ID
        name: Person name
        embeddings: List of embedding dicts with 'vector' key
        
    Returns:
        True if successful
    """
    if not _sqlite_db:
        return False
    
    try:
        _sqlite_db.add_person(person_id, name)
        
        if embeddings:
            for emb in embeddings:
                vector = emb.get("vector") if isinstance(emb, dict) else emb
                if vector:
                    _sqlite_db.add_embedding(person_id, vector)
        
        return True
    except Exception as e:
        _LOGGER.error(f"Failed to save person to SQLite: {e}")
        return False


async def _delete_person_from_sqlite(person_id: str) -> bool:
    """Delete a person from SQLite database.
    
    Args:
        person_id: Person ID to delete
        
    Returns:
        True if successful
    """
    if not _sqlite_db:
        return False
    
    try:
        return _sqlite_db.delete_person(person_id, hard_delete=True)
    except Exception as e:
        _LOGGER.error(f"Failed to delete person from SQLite: {e}")
        return False


async def _rename_person_in_sqlite(person_id: str, new_name: str) -> bool:
    """Rename a person in SQLite database.
    
    Args:
        person_id: Person ID to rename
        new_name: New name for the person
        
    Returns:
        True if successful
    """
    if not _sqlite_db:
        return False
    
    try:
        return _sqlite_db.update_person(person_id, name=new_name)
    except Exception as e:
        _LOGGER.error(f"Failed to rename person in SQLite: {e}")
        return False


async def _add_embedding_to_sqlite(person_id: str, embedding: list, thumb: str = None) -> bool:
    """Add an embedding to a person in SQLite.
    
    Args:
        person_id: Person ID
        embedding: Embedding vector
        thumb: Optional thumbnail path
        
    Returns:
        True if successful
    """
    if not _sqlite_db:
        return False
    
    try:
        result = _sqlite_db.add_embedding(person_id, embedding, source_image=thumb)
        return result > 0
    except Exception as e:
        _LOGGER.error(f"Failed to add embedding to SQLite: {e}")
        return False


def enable_sqlite_backend(config_path: str = "/config") -> bool:
    """Initialize SQLite backend.
    
    Args:
        config_path: Home Assistant config path
        
    Returns:
        True if successfully enabled
    """
    global _sqlite_db
    
    try:
        from .database import get_database
        
        _sqlite_db = get_database(config_path)
        if _sqlite_db.initialize():
            _LOGGER.info("SQLite backend initialized for people database")
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
    """Close SQLite database connection."""
    global _sqlite_db
    
    if _sqlite_db:
        from .database import close_database
        close_database()
    
    _sqlite_db = None
    _LOGGER.info("SQLite backend disabled")


def is_sqlite_enabled() -> bool:
    """Check if SQLite backend is enabled.
    
    Returns:
        True if SQLite is active
    """
    return _sqlite_db is not None


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
    
    Used for analytics and movement profile tracking.
    
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
        History entry ID or -1 if failed
    """
    if not _sqlite_db:
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
    
    Args:
        days: Number of days to analyze
        
    Returns:
        Statistics dict
    """
    if not _sqlite_db:
        return {}
    
    return _sqlite_db.get_recognition_stats(days)


async def get_database_stats() -> dict:
    """Get database statistics.
    
    Returns:
        Dict with counts and sizes
    """
    if _sqlite_db:
        return _sqlite_db.get_db_stats()
    
    return {
        "backend": "sqlite",
        "initialized": False
    }
