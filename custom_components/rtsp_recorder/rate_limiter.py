"""Rate Limiter for WebSocket API handlers.

Token-bucket rate limiter for the rtsp_recorder WebSocket API. Designed to be
rolled out safely on a live system:

- Three modes (``RateLimitConfig.mode``): ``off`` (default, fully inert),
  ``monitor`` (shadow mode — counts what *would* be throttled without throttling,
  to gather a real load profile), and ``enforce`` (actually drops over-budget
  requests). The default is ``off``, so simply shipping this module changes no
  behaviour until an operator opts in.
- One write-bucket per HA user (``user_<id>``). Anonymous/system connections
  without a user are never limited. Read/poll handlers are intentionally NOT
  decorated (see websocket_handlers.py).
- Fail-open: any error in the limiter lets the wrapped handler run normally; the
  limiter must never silently eat a legitimate request.
- Process-stable: a single instance lives in ``hass.data[DOMAIN]['rate_limiter']``
  and is reconfigured (not rebuilt) on config-entry reload, so token state and the
  shadow profile survive the reloads that write-handlers trigger.

Security: HIGH-001 Rate Limiting (Audit Report v1.1.0). Scope: rtsp_recorder
WebSocket write/expensive handlers only — HTTP views (thumbnail/video) and HA-core
media_source are out of scope (see CHANGELOG). exceptions.RateLimitExceededError
is intentionally unused (the WS-conformant signal is send_result(rate_limited=True)).
"""
import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar, Coroutine
from functools import wraps

try:  # package context (production)
    from .const import DOMAIN
except ImportError:  # pragma: no cover - standalone import in tests
    try:
        from const import DOMAIN
    except ImportError:
        DOMAIN = "rtsp_recorder"

_LOGGER = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Coroutine[Any, Any, Any]])

VALID_MODES = ("off", "monitor", "enforce")


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting.

    ``mode`` is the single source of truth (off/monitor/enforce, default off).
    The legacy ``enabled`` bool is kept so existing constructor calls do not raise,
    but it is DERIVED from ``mode`` in __post_init__ (enabled == mode != 'off') and
    no longer controls behaviour on its own. ``cooldown_seconds`` is a deprecated
    NO-OP (the global cooldown mechanic was removed); the field is kept only for
    backward compatibility with existing tests / get_stats.
    """
    requests_per_window: int = 60
    window_seconds: int = 60
    burst_size: int = 10
    cooldown_seconds: int = 5  # deprecated NO-OP, kept for compatibility
    enabled: bool = True       # derived from mode in __post_init__
    mode: str = "off"

    def __post_init__(self):
        if self.mode not in VALID_MODES:
            self.mode = "off"
        # mode is authoritative; keep `enabled` as a derived legacy read.
        self.enabled = self.mode != "off"


@dataclass
class ClientState:
    """State tracking for a single client (one HA user)."""
    tokens: float = 0.0
    last_update: float = field(default_factory=time.time)
    cooldown_until: float = 0.0  # deprecated, unused
    request_count: int = 0
    blocked_count: int = 0


class RateLimiter:
    """Token-bucket rate limiter for the WebSocket API.

    New clients start with a full bucket so an initial burst (up to burst_size) is
    allowed. There is no cooldown: enforce drops only the single over-budget
    request, never a cross-tab/endpoint lockout.
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        # Lazy lock: created on first use inside the running event loop. Avoids
        # binding asyncio.Lock() to the wrong loop at import/construction time.
        self._lock: asyncio.Lock | None = None
        self._clients: dict[str, ClientState] = {}
        # Monotone, prune-/reconfigure-proof counters for the shadow profile.
        self._total_requests_seen = 0
        self._total_would_block_seen = 0
        self._endpoint_would_block: dict[str, int] = defaultdict(int)
        self._recompute()

    def _recompute(self) -> None:
        """(Re)derive refill rate / capacity from config, defensively clamped."""
        self._window = max(1, int(self.config.window_seconds))
        rpw = max(1, int(self.config.requests_per_window))
        burst = max(0, int(self.config.burst_size))
        self._refill_rate = rpw / self._window
        self._max_tokens = float(rpw + burst)

    def reconfigure(self, config: RateLimitConfig) -> None:
        """Apply a new config WITHOUT resetting client state / counters.

        Called on config-entry reload so the shadow profile and token buckets
        survive the reloads that write-handlers trigger.
        """
        self.config = config
        self._recompute()

    def _get_client_id(self, connection) -> str | None:
        """Return ``user_<id>`` or None (None => do not rate-limit)."""
        try:
            user = getattr(connection, "user", None)
            if user is not None and getattr(user, "id", None):
                return f"user_{user.id}"
        except Exception:  # pragma: no cover - defensive
            return None
        return None

    def _refill(self, client: ClientState, now: float) -> None:
        elapsed = now - client.last_update
        client.tokens = min(client.tokens + elapsed * self._refill_rate, self._max_tokens)
        client.last_update = now

    def _prune(self, now: float) -> None:
        """Drop idle clients (no activity for > 2 windows) to bound memory."""
        cutoff = now - 2 * self._window
        stale = [cid for cid, c in self._clients.items() if c.last_update < cutoff]
        for cid in stale:
            del self._clients[cid]

    async def check_rate_limit(self, connection, endpoint: str) -> tuple[bool, str]:
        """Return (allowed, message).

        off     -> always (True, "") with no state touched.
        monitor -> mirrors enforce's accounting but never blocks (counts
                   would-block); returns (True, "").
        enforce -> drops the single over-budget request (False, message).
        """
        mode = self.config.mode
        if mode == "off":
            return True, ""

        client_id = self._get_client_id(connection)
        if client_id is None:
            # Anonymous/system connection: never limited.
            return True, ""

        if self._lock is None:
            self._lock = asyncio.Lock()

        async with self._lock:
            now = time.time()
            self._prune(now)
            client = self._clients.get(client_id)
            if client is None:
                client = ClientState(tokens=self._max_tokens, last_update=now)
                self._clients[client_id] = client

            self._refill(client, now)
            self._total_requests_seen += 1

            if client.tokens < 1:
                client.blocked_count += 1
                self._total_would_block_seen += 1
                self._endpoint_would_block[endpoint] += 1
                if mode == "monitor":
                    _LOGGER.info(
                        "WOULD rate-limit %s on %s (shadow mode; not blocked)",
                        client_id, endpoint,
                    )
                    return True, ""
                _LOGGER.warning(
                    "Rate limit exceeded for %s on %s (blocked=%d)",
                    client_id, endpoint, client.blocked_count,
                )
                return False, "Rate limit exceeded, please slow down."

            client.tokens -= 1
            client.request_count += 1
            return True, ""

    def get_stats(self) -> dict:
        """Statistics for observability (read-only)."""
        return {
            "mode": self.config.mode,
            "enabled": self.config.enabled,
            "active_clients": len(self._clients),
            "total_requests_seen": self._total_requests_seen,
            "total_would_block_seen": self._total_would_block_seen,
            "would_block_by_endpoint": dict(self._endpoint_would_block),
            "config": {
                "mode": self.config.mode,
                "requests_per_window": self.config.requests_per_window,
                "window_seconds": self.config.window_seconds,
                "burst_size": self.config.burst_size,
                "cooldown_seconds": self.config.cooldown_seconds,  # deprecated NO-OP
            },
        }

    def reset_client(self, connection) -> None:
        client_id = self._get_client_id(connection)
        if client_id and client_id in self._clients:
            del self._clients[client_id]

    def reset_all(self) -> None:
        self._clients.clear()

    def limit(self, endpoint: str | None = None) -> Callable[[F], F]:
        """Instance-bound decorator (used in tests). Production uses the
        module-level :func:`limit` (late-binding via hass.data)."""
        def decorator(func: F) -> F:
            ep = endpoint or func.__name__

            @wraps(func)
            async def wrapper(hass, connection, msg):
                return await _apply_limit(self, ep, func, hass, connection, msg)

            return wrapper  # type: ignore
        return decorator


async def _apply_limit(limiter, endpoint, func, hass, connection, msg):
    """Shared decorator body: fail-open rate-limit gate around a WS handler.

    The ``check_rate_limit`` call is wrapped in try/except (fail-open). The real
    handler call sits OUTSIDE the try, so genuine handler exceptions are never
    swallowed.
    """
    allowed, message = True, ""
    try:
        if limiter is not None:
            allowed, message = await limiter.check_rate_limit(connection, endpoint)
    except Exception:  # pragma: no cover - defensive fail-open
        _LOGGER.exception("rate limiter errored; failing open for %s", endpoint)
        allowed = True
    if not allowed:
        connection.send_result(
            msg["id"], {"success": False, "rate_limited": True, "message": message}
        )
        return None
    return await func(hass, connection, msg)


def limit(endpoint: str | None = None) -> Callable[[F], F]:
    """Module-level, late-binding rate-limit decorator for WS handlers.

    The wrapped handler resolves the process-stable limiter from
    ``hass.data[DOMAIN]['rate_limiter']`` per call (so reconfigure() takes effect
    immediately and there is no closure capture of a stale instance). If no limiter
    is present, the handler runs unthrottled (fail-open).

    Must be the INNERMOST decorator (below @websocket_command / @async_response):

        @websocket_api.websocket_command({...})
        @websocket_api.async_response
        @limit("rtsp_recorder/add_person")
        async def ws_add_person(hass, connection, msg): ...
    """
    def decorator(func: F) -> F:
        ep = endpoint or func.__name__

        @wraps(func)
        async def wrapper(hass, connection, msg):
            limiter = None
            try:
                data = getattr(hass, "data", None)
                if data:
                    limiter = data.get(DOMAIN, {}).get("rate_limiter")
            except Exception:  # pragma: no cover - defensive
                limiter = None
            return await _apply_limit(limiter, ep, func, hass, connection, msg)

        return wrapper  # type: ignore
    return decorator


# Global instance — TEST SHIM ONLY. Production uses hass.data[DOMAIN]['rate_limiter'].
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter (default mode='off' — inert unless configured)."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(RateLimitConfig(
            requests_per_window=120,
            window_seconds=60,
            burst_size=60,
            mode="off",
        ))
    return _rate_limiter


def configure_rate_limiter(config: RateLimitConfig) -> RateLimiter:
    """Configure and return the global rate limiter (test shim)."""
    global _rate_limiter
    _rate_limiter = RateLimiter(config)
    return _rate_limiter
