"""Unit tests for Rate Limiter module.

Feature: MED-001 Unit Test Framework (Audit Report v1.1.0)
"""
import asyncio
import time
from unittest.mock import MagicMock

import pytest

# Import module under test (adjust path as needed)
import sys
from pathlib import Path

# Add parent path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rtsp_recorder"))

try:
    from rate_limiter import RateLimiter, RateLimitConfig, get_rate_limiter
except ImportError:
    # Fallback for test runner
    RateLimiter = None
    RateLimitConfig = None


@pytest.mark.unit
class TestRateLimitConfig:
    """Tests for RateLimitConfig."""
    
    def test_default_values(self):
        """Test default configuration values."""
        if RateLimitConfig is None:
            pytest.skip("Module not available")
            
        config = RateLimitConfig()
        
        assert config.requests_per_window == 60
        assert config.window_seconds == 60
        assert config.burst_size == 10
        assert config.cooldown_seconds == 5
        assert config.enabled is True
    
    def test_custom_values(self):
        """Test custom configuration values."""
        if RateLimitConfig is None:
            pytest.skip("Module not available")
            
        config = RateLimitConfig(
            requests_per_window=100,
            window_seconds=30,
            burst_size=20,
            cooldown_seconds=10,
            enabled=False,
        )
        
        assert config.requests_per_window == 100
        assert config.window_seconds == 30
        assert config.burst_size == 20
        assert config.cooldown_seconds == 10
        assert config.enabled is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestRateLimiter:
    """Tests for RateLimiter."""
    
    @pytest.fixture
    def limiter(self):
        """Create a rate limiter with fast settings for testing."""
        if RateLimiter is None:
            pytest.skip("Module not available")
            
        config = RateLimitConfig(
            requests_per_window=10,
            window_seconds=1,
            burst_size=5,
            cooldown_seconds=1,
            enabled=True,
        )
        return RateLimiter(config)
    
    @pytest.fixture
    def mock_connection(self):
        """Create mock WebSocket connection."""
        conn = MagicMock()
        conn.user = MagicMock()
        conn.user.id = "test_user"
        return conn
    
    async def test_allows_requests_under_limit(self, limiter, mock_connection):
        """Test that requests under limit are allowed."""
        for i in range(5):
            allowed, error = await limiter.check_rate_limit(mock_connection, "test_endpoint")
            assert allowed is True
            assert error == ""
    
    async def test_blocks_requests_over_limit(self, limiter, mock_connection):
        """Test that requests over limit are blocked."""
        # Use up all tokens quickly
        for _ in range(20):
            await limiter.check_rate_limit(mock_connection, "test_endpoint")
        
        # This should be blocked
        allowed, error = await limiter.check_rate_limit(mock_connection, "test_endpoint")
        assert allowed is False
        assert "Rate limit exceeded" in error
    
    async def test_tokens_refill_over_time(self, limiter, mock_connection):
        """Test that tokens refill over time."""
        # Use some tokens
        for _ in range(5):
            await limiter.check_rate_limit(mock_connection, "test_endpoint")
        
        # Wait for refill
        await asyncio.sleep(0.5)
        
        # Should have some tokens again
        allowed, error = await limiter.check_rate_limit(mock_connection, "test_endpoint")
        assert allowed is True
    
    async def test_disabled_limiter_allows_all(self, mock_connection):
        """Test that disabled limiter allows all requests."""
        if RateLimiter is None:
            pytest.skip("Module not available")
            
        config = RateLimitConfig(enabled=False)
        limiter = RateLimiter(config)
        
        # All requests should be allowed
        for _ in range(100):
            allowed, error = await limiter.check_rate_limit(mock_connection, "test_endpoint")
            assert allowed is True
    
    def test_get_stats(self, limiter, mock_connection):
        """Test statistics retrieval."""
        stats = limiter.get_stats()
        
        assert "enabled" in stats
        assert "total_clients" in stats
        assert "total_requests" in stats
        assert "config" in stats
    
    async def test_different_clients_tracked_separately(self, limiter):
        """Test that different clients have separate rate limits."""
        conn1 = MagicMock()
        conn1.user = MagicMock()
        conn1.user.id = "user_1"
        
        conn2 = MagicMock()
        conn2.user = MagicMock()
        conn2.user.id = "user_2"
        
        # Use up tokens for user 1
        for _ in range(20):
            await limiter.check_rate_limit(conn1, "test")
        
        # User 2 should still be allowed
        allowed, _ = await limiter.check_rate_limit(conn2, "test")
        assert allowed is True
    
    def test_reset_client(self, limiter, mock_connection):
        """Test client reset."""
        # Make some requests
        asyncio.get_event_loop().run_until_complete(
            limiter.check_rate_limit(mock_connection, "test")
        )
        
        # Reset
        limiter.reset_client(mock_connection)
        
        # Stats should be cleared for this client
        stats = limiter.get_stats()
        assert stats["total_clients"] == 0


@pytest.mark.unit
class TestRateLimiterDecorator:
    """Tests for the limit decorator."""
    
    def test_decorator_applies(self):
        """Test that decorator can be applied to function."""
        if RateLimiter is None:
            pytest.skip("Module not available")
            
        limiter = RateLimiter()
        
        @limiter.limit("test_endpoint")
        async def test_handler(hass, connection, msg):
            return "success"
        
        assert asyncio.iscoroutinefunction(test_handler)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
