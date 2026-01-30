"""Face matching utilities for RTSP Recorder Integration.

This module contains functions for face embedding manipulation and matching:
- Cosine similarity calculation
- Embedding normalization
- Centroid computation
- Face matching against people database
"""
from typing import Any


def _cosine_similarity_simple(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two embedding vectors.
    
    Args:
        a: First embedding vector
        b: Second embedding vector
        
    Returns:
        Cosine similarity score between 0 and 1
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _normalize_embedding_simple(values: list[float]) -> list[float]:
    """Normalize an embedding vector to unit length.
    
    Args:
        values: Embedding vector
        
    Returns:
        Normalized embedding vector
    """
    if not values:
        return []
    norm = sum((v * v) for v in values) ** 0.5
    if norm == 0:
        return values
    return [v / norm for v in values]


def _compute_centroid(embeddings: list) -> list[float] | None:
    """Compute the centroid (average) of multiple embeddings.
    
    This creates a single representative vector for a person,
    making face matching faster and more robust.
    
    Args:
        embeddings: List of embedding vectors (can be dicts with "vector" key or plain lists)
        
    Returns:
        Normalized centroid vector or None if no valid embeddings
    """
    if not embeddings:
        return None
    
    vectors = []
    for emb in embeddings:
        if isinstance(emb, dict):
            emb = emb.get("vector", [])
        if isinstance(emb, list) and len(emb) > 0:
            try:
                vec = [float(x) for x in emb]
                vectors.append(vec)
            except (TypeError, ValueError):
                continue
    
    if not vectors:
        return None
    
    # All vectors should have the same dimension
    dim = len(vectors[0])
    centroid = [0.0] * dim
    
    for vec in vectors:
        if len(vec) != dim:
            continue
        for i in range(dim):
            centroid[i] += vec[i]
    
    n = len(vectors)
    if n == 0:
        return None
    centroid = [c / n for c in centroid]
    
    # Normalize the centroid for cosine similarity
    norm = sum(c * c for c in centroid) ** 0.5
    if norm > 0:
        centroid = [c / norm for c in centroid]
    
    return centroid


def _update_person_centroid(person: dict[str, Any]) -> dict[str, Any]:
    """Update the centroid for a single person based on their embeddings.
    
    Args:
        person: Person dict with "embeddings" list
        
    Returns:
        Updated person dict with "centroid" key
    """
    embeddings = person.get("embeddings", [])
    if embeddings:
        centroid = _compute_centroid(embeddings)
        if centroid:
            person["centroid"] = centroid
    return person


def _update_all_centroids(data: dict[str, Any]) -> dict[str, Any]:
    """Update centroids for all people in the database.
    
    Args:
        data: People database dict with "people" list
        
    Returns:
        Updated database dict
    """
    for person in data.get("people", []):
        _update_person_centroid(person)
    return data


def _match_face_simple(
    embedding: list[float], 
    people: list[dict[str, Any]], 
    threshold: float = 0.6
) -> dict[str, Any] | None:
    """Match a face embedding against the people database.
    
    Uses centroid-based matching for faster and more robust results.
    Falls back to comparing against all embeddings if no centroid exists.
    
    Args:
        embedding: Face embedding vector to match
        people: List of person dicts from people database
        threshold: Minimum similarity score for a match
        
    Returns:
        Match result dict with person_id, name, similarity or None
    """
    if not embedding or not people:
        return None
    
    best = None
    best_score = -1.0
    
    for person in people:
        p_id = person.get("id")
        p_name = person.get("name")
        
        # Try centroid first (faster, more robust)
        centroid = person.get("centroid")
        if centroid:
            try:
                centroid_list = [float(v) for v in centroid]
                score = _cosine_similarity_simple(embedding, centroid_list)
                if score > best_score:
                    best_score = score
                    best = {"person_id": p_id, "name": p_name, "similarity": round(float(score), 4)}
                continue  # Skip individual embeddings if centroid exists
            except (TypeError, ValueError):
                pass  # Fall through to individual embeddings
        
        # Fallback: compare against all embeddings
        for emb in person.get("embeddings", []) or []:
            if isinstance(emb, dict):
                emb_vec = emb.get("vector", [])
            else:
                emb_vec = emb
            if not emb_vec or not isinstance(emb_vec, list):
                continue
            try:
                emb_list = [float(v) for v in emb_vec]
            except (TypeError, ValueError):
                continue
            score = _cosine_similarity_simple(embedding, emb_list)
            if score > best_score:
                best_score = score
                best = {"person_id": p_id, "name": p_name, "similarity": round(float(score), 4)}
    
    if best and best_score >= float(threshold):
        return best
    return None
