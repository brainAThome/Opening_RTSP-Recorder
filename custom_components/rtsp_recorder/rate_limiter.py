"""Rate Limiter for WebSocket API handlers.

This module provides rate limiting functionality to prevent DoS attacks
and ensure fair resource usage across all clients.

Implements a token bucket algorithm for smooth rate limiting.

Security Fix: HIGH-001 Rate Limiting (Audit Report v1.1.0)
"""
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar, Coroutine
from functools import wraps

_LOGGER = logging.getLogger(__name__)

# Type for async functions
F = TypeVar('F', bound=Callable[..., Coroutine[Any, Any, Any]])


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    # Requests per window
    requests_per_window: int = 60
    # Window size in seconds
    window_seconds: int = 60
    # Burst allowance (extra requests allowed in short bursts)
    burst_size: int = 10
    # Cooldown after hitting limit (seconds)
    cooldown_seconds: int = 5
    # Enable/disable rate limiting
    enabled: bool = True


@dataclass
class ClientState:
    """State tracking for a single client."""
    tokens: float = 0.0
    last_update: float = field(default_factory=time.time)
    cooldown_until: float = 0.0
    request_count: int = 0
    blocked_count: int = 0


class RateLimiter:
    """Token bucket rate limiter for WebSocket API.
    
    Uses token bucket algorithm which allows bursting while maintaining
    average rate limits. This provides better UX than strict per-second limits.
    
    Example:
        limiter = RateLimiter(RateLimitConfig(requests_per_window=60, window_seconds=60))
        
        @limiter.limit("ws_get_cameras")
        async def ws_get_cameras(hass, connection, msg):
            ...
    """
    
    def __init__(self, config: RateLimitConfig | None = None):
        """Initialize rate limiter.
        
        Args:
            config: Rate limit configuration, uses defaults if None
        """
        self.config = config or RateLimitConfig()
        self._clients: dict[str, ClientState] = defaultdict(ClientState)
        self._lock = asyncio.Lock()
        
        # Calculate token refill rate
        # tokens_per_second = requests_per_window / window_seconds
        self._refill_rate = self.config.requests_per_window / self.config.window_seconds
        self._max_tokens = self.config.requests_per_window + self.config.burst_size
        
    def _get_client_id(self, connection) -> str:
        """Extract client identifier from WebSocket connection."""
        # Use connection ID or user ID for identification
        try:
            if hasattr(connection, 'user') and connection.user:
                return f"user_{connection.user.id}"
            if hasattr(connection, 'context') and connection.context:
                return f"ctx_{connection.context.id}"
            return f"conn_{id(connection)}"
        except Exception:
            return f"unknown_{id(connection)}"
    
    async def _refill_tokens(self, client: ClientState) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - client.last_update
        
        # Add tokens based on elapsed time
        new_tokens = client.tokens + (elapsed * self._refill_rate)
        client.tokens = min(new_tokens, self._max_tokens)
        client.last_update = now
    
    async def check_rate_limit(self, connection, endpoint: str) -> tuple[bool, str]:
        """Check if request should be allowed.
        
        Args:
            connection: WebSocket connection
            endpoint: API endpoint name
            
        Returns:
            Tuple of (allowed, error_message)
        """
        if not self.config.enabled:
            return True, ""
            
        client_id = self._get_client_id(connection)
        
        async with self._lock:
            client = self._clients[client_id]
            
            # Check cooldown
            now = time.time()
            if client.cooldown_until > now:
                remaining = int(client.cooldown_until - now)
                client.blocked_count += 1
                return False, f"Rate limit exceeded. Retry in {remaining}s"
            
            # Refill tokens
            await self._refill_tokens(client)
            
            # Check if we have tokens
            if client.tokens < 1:
                # Enter cooldown
                client.cooldown_until = now + self.config.cooldown_seconds
                client.blocked_count += 1
                _LOGGER.warning(
                    f"Rate limit exceeded for {client_id} on {endpoint}. "
                    f"Requests: {client.request_count}, Blocked: {client.blocked_count}"
                )
                return False, f"Rate limit exceeded. Retry in {self.config.cooldown_seconds}s"
            
            # Consume a token
            client.tokens -= 1
            client.request_count += 1
            
            return True, ""
    
    def limit(self, endpoint: str | None = None) -> Callable[[F], F]:
        """Decorator to apply rate limiting to a WebSocket handler.
        
        Args:
            endpoint: Optional endpoint name for logging
            
        Returns:
            Decorator function
        """
        def decorator(func: F) -> F:
            ep_name = endpoint or func.__name__
            
            @wraps(func)
            async def wrapper(hass, connection, msg):
                allowed, error = await self.check_rate_limit(connection, ep_name)
                if not allowed:
                    connection.send_error(msg["id"], "rate_limited", error)
                    return
                return await func(hass, connection, msg)
            
            return wrapper  # type: ignore
        return decorator
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        total_requests = sum(c.request_count for c in self._clients.values())
        total_blocked = sum(c.blocked_count for c in self._clients.values())
        
        return {
            "enabled": self.config.enabled,
            "total_clients": len(self._clients),
            "total_requests": total_requests,
            "total_blocked": total_blocked,
            "config": {
                "requests_per_window": self.config.requests_per_window,
                "window_seconds": self.config.window_seconds,
                "burst_size": self.config.burst_size,
                "cooldown_seconds": self.config.cooldown_seconds,
            }
        }
    
    def reset_client(self, connection) -> None:
        """Reset rate limit state for a client."""
        client_id = self._get_client_id(connection)
        if client_id in self._clients:
            del self._clients[client_id]
    
    def reset_all(self) -> None:
        """Reset all rate limit state."""
        self._clients.clear()


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(RateLimitConfig(
            requests_per_window=120,  # 2 requests per second average
            window_seconds=60,
            burst_size=30,  # Allow bursts of up to 30 extra requests
            cooldown_seconds=3,
            enabled=True,
        ))
    return _rate_limiter


def configure_rate_limiter(config: RateLimitConfig) -> RateLimiter:
    """Configure and return the global rate limiter."""
    global _rate_limiter
    _rate_limiter = RateLimiter(config)
    return _rate_limiter
