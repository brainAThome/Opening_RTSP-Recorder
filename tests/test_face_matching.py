"""Unit tests for Face Matching module.

Feature: Test-Coverage Erweiterung (Audit Report v1.1.1)

Tests for:
- Cosine similarity calculation
- Embedding normalization
- Centroid computation
- Face matching against people database
"""
import pytest
import sys
import math
from pathlib import Path

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rtsp_recorder"))

try:
    from face_matching import (
        _cosine_similarity_simple,
        _normalize_embedding_simple,
        _compute_centroid,
        _update_person_centroid,
        find_best_match,
    )
except ImportError as e:
    _cosine_similarity_simple = None
    print(f"Import error: {e}")


@pytest.mark.unit
class TestCosineSimilarity:
    """Tests for cosine similarity calculation."""
    
    def test_identical_vectors(self):
        """Test similarity of identical vectors is 1.0."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        vec = [1.0, 0.0, 0.0]
        similarity = _cosine_similarity_simple(vec, vec)
        
        assert abs(similarity - 1.0) < 0.0001
    
    def test_orthogonal_vectors(self):
        """Test orthogonal vectors have 0 similarity."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        
        similarity = _cosine_similarity_simple(vec_a, vec_b)
        
        assert abs(similarity) < 0.0001
    
    def test_opposite_vectors(self):
        """Test opposite vectors have -1.0 similarity."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [-1.0, 0.0, 0.0]
        
        similarity = _cosine_similarity_simple(vec_a, vec_b)
        
        assert abs(similarity + 1.0) < 0.0001
    
    def test_similar_vectors(self):
        """Test similar vectors have high similarity."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        vec_a = [1.0, 0.1, 0.0]
        vec_b = [1.0, 0.2, 0.0]
        
        similarity = _cosine_similarity_simple(vec_a, vec_b)
        
        # Should be close to 1
        assert similarity > 0.99
    
    def test_empty_vectors(self):
        """Test empty vectors return 0."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        assert _cosine_similarity_simple([], []) == 0.0
        assert _cosine_similarity_simple([1.0], []) == 0.0
        assert _cosine_similarity_simple([], [1.0]) == 0.0
    
    def test_mismatched_lengths(self):
        """Test mismatched vector lengths return 0."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        vec_a = [1.0, 0.0]
        vec_b = [1.0, 0.0, 0.0]
        
        similarity = _cosine_similarity_simple(vec_a, vec_b)
        
        assert similarity == 0.0
    
    def test_zero_vector(self):
        """Test zero vector returns 0."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        zero_vec = [0.0, 0.0, 0.0]
        normal_vec = [1.0, 0.0, 0.0]
        
        assert _cosine_similarity_simple(zero_vec, normal_vec) == 0.0
        assert _cosine_similarity_simple(normal_vec, zero_vec) == 0.0
    
    def test_large_vectors(self):
        """Test with realistic 128-dim face embedding."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        import random
        random.seed(42)  # Reproducible
        
        # Create two similar 128-dim vectors
        vec_a = [random.gauss(0, 1) for _ in range(128)]
        vec_b = [v + random.gauss(0, 0.1) for v in vec_a]  # Slightly perturbed
        
        similarity = _cosine_similarity_simple(vec_a, vec_b)
        
        # Should be very similar
        assert similarity > 0.95


@pytest.mark.unit
class TestNormalizeEmbedding:
    """Tests for embedding normalization."""
    
    def test_normalize_unit_vector(self):
        """Test normalizing already unit vector."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        vec = [1.0, 0.0, 0.0]
        normalized = _normalize_embedding_simple(vec)
        
        assert abs(normalized[0] - 1.0) < 0.0001
        assert abs(normalized[1]) < 0.0001
        assert abs(normalized[2]) < 0.0001
    
    def test_normalize_non_unit_vector(self):
        """Test normalizing non-unit vector."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        vec = [3.0, 4.0, 0.0]  # Length 5
        normalized = _normalize_embedding_simple(vec)
        
        # Check normalized to unit length
        norm = math.sqrt(sum(v * v for v in normalized))
        assert abs(norm - 1.0) < 0.0001
        
        # Check direction preserved
        assert abs(normalized[0] - 0.6) < 0.0001
        assert abs(normalized[1] - 0.8) < 0.0001
    
    def test_normalize_empty_vector(self):
        """Test normalizing empty vector."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        result = _normalize_embedding_simple([])
        assert result == []
    
    def test_normalize_zero_vector(self):
        """Test normalizing zero vector."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        vec = [0.0, 0.0, 0.0]
        normalized = _normalize_embedding_simple(vec)
        
        # Zero vector should remain zero (can't normalize)
        assert normalized == vec


@pytest.mark.unit
class TestComputeCentroid:
    """Tests for centroid computation."""
    
    def test_single_embedding(self):
        """Test centroid of single embedding."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        embeddings = [[1.0, 0.0, 0.0]]
        centroid = _compute_centroid(embeddings)
        
        # Centroid of single vector is that vector (normalized)
        assert centroid is not None
        assert abs(centroid[0] - 1.0) < 0.0001
    
    def test_multiple_embeddings(self):
        """Test centroid of multiple embeddings."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
        centroid = _compute_centroid(embeddings)
        
        # Average should be [0.5, 0.5, 0.0], then normalized
        assert centroid is not None
        assert len(centroid) == 3
        
        # Check it's normalized
        norm = math.sqrt(sum(v * v for v in centroid))
        assert abs(norm - 1.0) < 0.0001
    
    def test_empty_embeddings(self):
        """Test centroid of empty list."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        centroid = _compute_centroid([])
        assert centroid is None
    
    def test_embeddings_as_dicts(self):
        """Test centroid with dict format embeddings."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        embeddings = [
            {"vector": [1.0, 0.0, 0.0], "id": "1"},
            {"vector": [0.0, 1.0, 0.0], "id": "2"},
        ]
        centroid = _compute_centroid(embeddings)
        
        assert centroid is not None
        assert len(centroid) == 3


@pytest.mark.unit
class TestUpdatePersonCentroid:
    """Tests for person centroid update."""
    
    def test_update_with_embeddings(self):
        """Test updating person centroid."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        person = {
            "id": "person_1",
            "name": "Test",
            "embeddings": [
                [1.0, 0.0, 0.0],
                [0.9, 0.1, 0.0],
            ]
        }
        
        updated = _update_person_centroid(person)
        
        assert "centroid" in updated
        assert updated["centroid"] is not None
        assert len(updated["centroid"]) == 3
    
    def test_update_without_embeddings(self):
        """Test updating person without embeddings."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        person = {
            "id": "person_1",
            "name": "Test",
            "embeddings": []
        }
        
        updated = _update_person_centroid(person)
        
        # Should not have centroid if no embeddings
        assert "centroid" not in updated or updated.get("centroid") is None


@pytest.mark.unit
class TestFindBestMatch:
    """Tests for face matching against database."""
    
    @pytest.fixture
    def sample_people(self):
        """Create sample people database."""
        return [
            {
                "id": "person_1",
                "name": "Alice",
                "centroid": [1.0, 0.0, 0.0],
            },
            {
                "id": "person_2", 
                "name": "Bob",
                "centroid": [0.0, 1.0, 0.0],
            },
            {
                "id": "person_3",
                "name": "Charlie",
                "centroid": [0.0, 0.0, 1.0],
            },
        ]
    
    def test_exact_match(self, sample_people):
        """Test exact match returns correct person."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        face_embedding = [1.0, 0.0, 0.0]  # Same as Alice
        
        match = find_best_match(face_embedding, sample_people, threshold=0.5)
        
        assert match is not None
        assert match["name"] == "Alice"
        assert match["confidence"] > 0.99
    
    def test_close_match(self, sample_people):
        """Test close match returns correct person."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        face_embedding = [0.95, 0.05, 0.0]  # Close to Alice
        
        match = find_best_match(face_embedding, sample_people, threshold=0.5)
        
        assert match is not None
        assert match["name"] == "Alice"
        assert match["confidence"] > 0.9
    
    def test_no_match_below_threshold(self, sample_people):
        """Test no match when below threshold."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        # Vector between Alice and Bob
        face_embedding = [0.5, 0.5, 0.0]
        
        # High threshold should not match
        match = find_best_match(face_embedding, sample_people, threshold=0.95)
        
        assert match is None
    
    def test_empty_people_list(self):
        """Test matching against empty people list."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        face_embedding = [1.0, 0.0, 0.0]
        
        match = find_best_match(face_embedding, [], threshold=0.5)
        
        assert match is None
    
    def test_people_without_centroid(self):
        """Test matching against people without centroids."""
        if _cosine_similarity_simple is None:
            pytest.skip("Module not available")
        
        people = [
            {"id": "person_1", "name": "Alice"},  # No centroid
        ]
        face_embedding = [1.0, 0.0, 0.0]
        
        match = find_best_match(face_embedding, people, threshold=0.5)
        
        assert match is None
