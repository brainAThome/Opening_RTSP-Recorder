"""People Database management for RTSP Recorder Integration.

This module handles all CRUD operations for the people database:
- Loading and saving the database file
- Atomic updates with proper locking
- Converting internal data to public view format
- In-memory caching for faster repeated reads

Performance optimizations:
- Cached reads avoid disk I/O when data hasn't changed
- Lock-protected atomic operations prevent race conditions
"""
import asyncio
import datetime
import json
import os
from typing import Any, Callable

from .const import PEOPLE_DB_VERSION
from .face_matching import _update_person_centroid


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
    
    Invalidates cache after write to ensure consistency.
    
    Args:
        path: Path to people database JSON file
        data: People database dict to save
    """
    async with _people_lock:
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
