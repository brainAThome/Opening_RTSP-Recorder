"""Face matching utilities for RTSP Recorder Integration.

This module contains functions for face embedding manipulation and matching:
- Cosine similarity calculation (NumPy-optimized when available)
- Embedding normalization
- Centroid computation
- Face matching against people database
"""
from typing import Any

# Try to use NumPy for faster vector operations
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None
    _HAS_NUMPY = False


def _cosine_similarity_simple(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two embedding vectors.
    
    Uses NumPy for ~10x faster computation when available.
    
    Args:
        a: First embedding vector
        b: Second embedding vector
        
    Returns:
        Cosine similarity score between 0 and 1
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    
    # NumPy-optimized path (10x faster)
    if _HAS_NUMPY:
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        if denom == 0:
            return 0.0
        return float(np.dot(va, vb) / denom)
    
    # Fallback: Pure Python
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
    
    # NumPy-optimized path
    if _HAS_NUMPY:
        # Filter vectors with matching dimensions
        dim = len(vectors[0])
        valid_vectors = [v for v in vectors if len(v) == dim]
        if not valid_vectors:
            return None
        
        arr = np.array(valid_vectors, dtype=np.float32)
        centroid = np.mean(arr, axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        return centroid.tolist()
    
    # Fallback: Pure Python
    dim = len(vectors[0])
    centroid = [0.0] * dim
    
    valid_count = 0
    for vec in vectors:
        if len(vec) != dim:
            continue
        for i in range(dim):
            centroid[i] += vec[i]
        valid_count += 1
    
    if valid_count == 0:
        return None
    centroid = [c / valid_count for c in centroid]
    
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


def _check_negative_samples(
    embedding: list[float], 
    person: dict[str, Any], 
    neg_threshold: float = 0.75
) -> bool:
    """Check if embedding matches any negative samples for this person.
    
    Negative samples are faces that were incorrectly matched to this person.
    If the new embedding is similar to a negative sample, it should be rejected.
    
    Args:
        embedding: Face embedding vector to check
        person: Person dict with optional "negative_embeddings" list
        neg_threshold: Similarity threshold to consider a negative match
        
    Returns:
        True if the embedding matches a negative sample (should be rejected)
    """
    negative_samples = person.get("negative_embeddings", [])
    if not negative_samples:
        return False
    
    for neg in negative_samples:
        # Handle both dict and list formats
        if isinstance(neg, dict):
            neg = neg.get("vector", [])
        if not neg or not isinstance(neg, list):
            continue
        try:
            neg_list = [float(v) for v in neg]
        except (TypeError, ValueError):
            continue
        
        sim = _cosine_similarity_simple(embedding, neg_list)
        if sim >= neg_threshold:
            return True  # This face is similar to a "NOT this person" sample
    
    return False


def _match_face_simple(
    embedding: list[float], 
    people: list[dict[str, Any]], 
    threshold: float = 0.6,
    check_negatives: bool = True,
    neg_threshold: float = 0.75
) -> dict[str, Any] | None:
    """Match a face embedding against the people database.
    
    Uses centroid-based matching for faster and more robust results.
    Falls back to comparing against all embeddings if no centroid exists.
    Also checks negative samples to prevent false matches.
    
    Args:
        embedding: Face embedding vector to match
        people: List of person dicts from people database
        threshold: Minimum similarity score for a match
        check_negatives: Whether to check negative samples (default True)
        neg_threshold: Threshold for negative sample matching
        
    Returns:
        Match result dict with person_id, name, similarity or None
    """
    if not embedding or not people:
        return None
    
    candidates = []
    
    for person in people:
        p_id = person.get("id")
        p_name = person.get("name")
        
        # Check negative samples first - skip this person if face matches a negative
        if check_negatives and _check_negative_samples(embedding, person, neg_threshold):
            continue  # Skip this person due to negative sample match
        
        best_score = -1.0
        
        # Try centroid first (faster, more robust)
        centroid = person.get("centroid")
        if centroid:
            try:
                centroid_list = [float(v) for v in centroid]
                score = _cosine_similarity_simple(embedding, centroid_list)
                if score >= threshold:
                    candidates.append({
                        "person_id": p_id, 
                        "name": p_name, 
                        "similarity": round(float(score), 4)
                    })
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
        
        if best_score >= threshold:
            candidates.append({
                "person_id": p_id,
                "name": p_name,
                "similarity": round(float(best_score), 4)
            })
    
    # Return the best candidate (highest similarity)
    if candidates:
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        return candidates[0]
    return None
