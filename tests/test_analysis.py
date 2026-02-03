"""Test suite for analysis module.

This module tests the core analysis functionality including:
- Embedding normalization
- Cosine similarity calculation
- Face matching algorithms
- Memory management constants
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestEmbeddingFunctions:
    """Tests for embedding manipulation functions."""
    
    def test_safe_float_list_valid(self):
        """Test _safe_float_list with valid inputs."""
        from analysis import _safe_float_list
        
        result = _safe_float_list([1, 2.5, "3.0", 4])
        assert result == [1.0, 2.5, 3.0, 4.0]
    
    def test_safe_float_list_invalid(self):
        """Test _safe_float_list filters invalid values."""
        from analysis import _safe_float_list
        
        result = _safe_float_list([1, "invalid", None, 3])
        assert result == [1.0, 3.0]
    
    def test_safe_float_list_empty(self):
        """Test _safe_float_list with empty list."""
        from analysis import _safe_float_list
        
        result = _safe_float_list([])
        assert result == []
    
    def test_normalize_embedding_valid(self):
        """Test _normalize_embedding produces unit vector."""
        from analysis import _normalize_embedding
        
        embedding = [3.0, 4.0]  # 3-4-5 triangle
        result = _normalize_embedding(embedding)
        
        # Should be normalized to unit length
        assert abs(result[0] - 0.6) < 0.001
        assert abs(result[1] - 0.8) < 0.001
    
    def test_normalize_embedding_zero(self):
        """Test _normalize_embedding handles zero vector."""
        from analysis import _normalize_embedding
        
        embedding = [0.0, 0.0, 0.0]
        result = _normalize_embedding(embedding)
        
        assert result == [0.0, 0.0, 0.0]
    
    def test_normalize_embedding_empty(self):
        """Test _normalize_embedding handles empty list."""
        from analysis import _normalize_embedding
        
        result = _normalize_embedding([])
        assert result == []
    
    def test_cosine_similarity_identical(self):
        """Test cosine similarity of identical vectors is 1.0."""
        from analysis import _cosine_similarity
        
        vec = [0.6, 0.8]
        result = _cosine_similarity(vec, vec)
        
        assert abs(result - 1.0) < 0.001
    
    def test_cosine_similarity_orthogonal(self):
        """Test cosine similarity of orthogonal vectors is 0.0."""
        from analysis import _cosine_similarity
        
        vec_a = [1.0, 0.0]
        vec_b = [0.0, 1.0]
        result = _cosine_similarity(vec_a, vec_b)
        
        assert abs(result) < 0.001
    
    def test_cosine_similarity_opposite(self):
        """Test cosine similarity of opposite vectors is -1.0."""
        from analysis import _cosine_similarity
        
        vec_a = [1.0, 0.0]
        vec_b = [-1.0, 0.0]
        result = _cosine_similarity(vec_a, vec_b)
        
        assert abs(result + 1.0) < 0.001
    
    def test_cosine_similarity_empty(self):
        """Test cosine similarity with empty vectors."""
        from analysis import _cosine_similarity
        
        result = _cosine_similarity([], [])
        assert result == 0.0
    
    def test_cosine_similarity_different_lengths(self):
        """Test cosine similarity with different length vectors."""
        from analysis import _cosine_similarity
        
        result = _cosine_similarity([1.0, 2.0], [1.0])
        assert result == 0.0


class TestCentroidComputation:
    """Tests for centroid computation."""
    
    def test_compute_centroid_single(self):
        """Test centroid of single embedding."""
        from analysis import _compute_centroid
        
        embeddings = [[0.6, 0.8]]
        result = _compute_centroid(embeddings)
        
        # Single embedding centroid is the embedding itself (normalized)
        assert result is not None
        assert len(result) == 2
    
    def test_compute_centroid_multiple(self):
        """Test centroid of multiple embeddings."""
        from analysis import _compute_centroid
        
        embeddings = [[1.0, 0.0], [0.0, 1.0]]
        result = _compute_centroid(embeddings)
        
        # Average of [1,0] and [0,1] is [0.5, 0.5], normalized
        assert result is not None
        assert len(result) == 2
        assert abs(result[0] - result[1]) < 0.001  # Should be equal
    
    def test_compute_centroid_empty(self):
        """Test centroid of empty list."""
        from analysis import _compute_centroid
        
        result = _compute_centroid([])
        assert result is None
    
    def test_compute_centroid_dict_format(self):
        """Test centroid with dict-formatted embeddings."""
        from analysis import _compute_centroid
        
        embeddings = [{"vector": [0.6, 0.8]}, {"vector": [0.8, 0.6]}]
        result = _compute_centroid(embeddings)
        
        assert result is not None
        assert len(result) == 2


class TestFaceMatching:
    """Tests for face matching logic."""
    
    def test_check_negative_samples_no_match(self):
        """Test negative sample check when no match."""
        from analysis import _check_negative_samples
        
        embedding = [0.6, 0.8]
        person = {"negative_embeddings": [[0.0, 1.0]]}
        
        result = _check_negative_samples(embedding, person)
        assert result is False
    
    def test_check_negative_samples_match(self):
        """Test negative sample check when matching."""
        from analysis import _check_negative_samples
        
        embedding = [0.6, 0.8]
        person = {"negative_embeddings": [[0.6, 0.8]]}  # Same vector
        
        result = _check_negative_samples(embedding, person)
        assert result is True
    
    def test_check_negative_samples_empty(self):
        """Test negative sample check with no negatives."""
        from analysis import _check_negative_samples
        
        embedding = [0.6, 0.8]
        person = {}
        
        result = _check_negative_samples(embedding, person)
        assert result is False
    
    def test_is_no_face_match(self):
        """Test no-face detection when matching."""
        from analysis import _is_no_face
        
        embedding = [0.6, 0.8]
        no_faces = [{"vector": [0.6, 0.8]}]
        
        result = _is_no_face(embedding, no_faces)
        assert result is True
    
    def test_is_no_face_no_match(self):
        """Test no-face detection when not matching."""
        from analysis import _is_no_face
        
        embedding = [0.6, 0.8]
        no_faces = [{"vector": [0.0, 1.0]}]
        
        result = _is_no_face(embedding, no_faces)
        assert result is False


class TestMemoryConstants:
    """Tests for memory management constants."""
    
    def test_max_faces_with_thumbs(self):
        """Test MAX_FACES_WITH_THUMBS is defined and reasonable."""
        from analysis import MAX_FACES_WITH_THUMBS
        
        assert MAX_FACES_WITH_THUMBS > 0
        assert MAX_FACES_WITH_THUMBS <= 100
    
    def test_max_thumb_size(self):
        """Test MAX_THUMB_SIZE is defined and reasonable."""
        from analysis import MAX_THUMB_SIZE
        
        assert MAX_THUMB_SIZE > 0
        assert MAX_THUMB_SIZE <= 200
    
    def test_thumb_jpeg_quality(self):
        """Test THUMB_JPEG_QUALITY is valid JPEG quality."""
        from analysis import THUMB_JPEG_QUALITY
        
        assert 1 <= THUMB_JPEG_QUALITY <= 100


class TestMatchFace:
    """Tests for the main face matching function."""
    
    def test_match_face_empty_people(self):
        """Test matching against empty people list."""
        from analysis import _match_face
        
        result = _match_face([0.6, 0.8], [], 0.7)
        assert result is None
    
    def test_match_face_empty_embedding(self):
        """Test matching with empty embedding."""
        from analysis import _match_face
        
        people = [{"id": "1", "name": "Test", "centroid": [0.6, 0.8]}]
        result = _match_face([], people, 0.7)
        
        assert result is None
    
    def test_match_face_with_centroid(self):
        """Test matching using centroid."""
        from analysis import _match_face
        
        embedding = [0.6, 0.8]
        people = [{"id": "1", "name": "Test", "centroid": [0.6, 0.8]}]
        
        result = _match_face(embedding, people, 0.7)
        
        assert result is not None
        assert result["name"] == "Test"
        assert result["similarity"] >= 0.7
    
    def test_match_face_below_threshold(self):
        """Test no match when below threshold."""
        from analysis import _match_face
        
        embedding = [1.0, 0.0]
        people = [{"id": "1", "name": "Test", "centroid": [0.0, 1.0]}]
        
        result = _match_face(embedding, people, 0.7)
        assert result is None
    
    def test_match_face_filters_negative(self):
        """Test that negative samples filter matches."""
        from analysis import _match_face
        
        embedding = [0.6, 0.8]
        people = [{
            "id": "1", 
            "name": "Test", 
            "centroid": [0.6, 0.8],
            "negative_embeddings": [[0.6, 0.8]]  # Same as query
        }]
        
        result = _match_face(embedding, people, 0.7)
        # Should be filtered due to negative match
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
