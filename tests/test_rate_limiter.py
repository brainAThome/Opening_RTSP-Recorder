"""Unit tests for the Rate Limiter module.

Feature: MED-001 Unit Test Framework. Updated for the v1.4.0-beta4 enterprise
wiring: 3-mode limiter (off/monitor/enforce), late-binding decorator, fail-open,
no cooldown, reconfigure(), user-only client ids.
"""
import asyncio
import time
from unittest.mock import MagicMock

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "rtsp_recorder"))

try:
    from rate_limiter import RateLimiter, RateLimitConfig, ClientState, get_rate_limiter, limit
except ImportError:
    RateLimiter = None
    RateLimitConfig = None
    ClientState = None
    limit = None

DOMAIN = "rtsp_recorder"


def _conn(user_id="test_user"):
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    if user_id is None:
        conn.user = None
    else:
        conn.user = MagicMock()
        conn.user.id = user_id
    return conn


@pytest.mark.unit
class TestRateLimitConfig:
    def test_default_values(self):
        if RateLimitConfig is None:
            pytest.skip("Module not available")
        config = RateLimitConfig()
        assert config.requests_per_window == 60
        assert config.window_seconds == 60
        assert config.burst_size == 10
        assert config.cooldown_seconds == 5  # deprecated NO-OP, still present
        # default is now OFF -> enabled derived False
        assert config.mode == "off"
        assert config.enabled is False

    def test_custom_values(self):
        if RateLimitConfig is None:
            pytest.skip("Module not available")
        config = RateLimitConfig(
            requests_per_window=100, window_seconds=30, burst_size=20,
            cooldown_seconds=10, enabled=False,
        )
        assert config.requests_per_window == 100
        assert config.window_seconds == 30
        assert config.burst_size == 20
        assert config.cooldown_seconds == 10
        assert config.enabled is False  # enabled=False -> mode off -> enabled False

    def test_enabled_kwarg_does_not_raise_and_mode_is_authoritative(self):
        if RateLimitConfig is None:
            pytest.skip("Module not available")
        # legacy enabled=True must NOT raise and must NOT silently enforce
        assert RateLimitConfig(enabled=True).mode == "off"
        assert RateLimitConfig(enabled=True).enabled is False
        # explicit mode wins and derives enabled
        assert RateLimitConfig(mode="enforce").enabled is True
        # invalid mode falls back to off
        assert RateLimitConfig(mode="bogus").mode == "off"

    def test_zero_values_do_not_crash(self):
        if RateLimiter is None:
            pytest.skip("Module not available")
        # window/requests 0 must not ZeroDivision at construction
        rl = RateLimiter(RateLimitConfig(requests_per_window=0, window_seconds=0, burst_size=-5, mode="enforce"))
        assert rl._refill_rate > 0
        assert rl._max_tokens >= 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestRateLimiterEnforce:
    @pytest.fixture
    def limiter(self):
        if RateLimiter is None:
            pytest.skip("Module not available")
        # max_tokens = 10 + 5 = 15
        return RateLimiter(RateLimitConfig(
            requests_per_window=10, window_seconds=1, burst_size=5, mode="enforce",
        ))

    async def test_allows_requests_under_limit(self, limiter):
        conn = _conn()
        for _ in range(5):
            allowed, error = await limiter.check_rate_limit(conn, "ep")
            assert allowed is True
            assert error == ""

    async def test_blocks_requests_over_limit(self, limiter):
        conn = _conn()
        for _ in range(20):
            await limiter.check_rate_limit(conn, "ep")
        allowed, error = await limiter.check_rate_limit(conn, "ep")
        assert allowed is False
        assert "Rate limit exceeded" in error

    async def test_no_cooldown_refill_unblocks_quickly(self, limiter):
        """Core defect fix: enforce drops only the single over-budget request;
        a short refill makes the next request allowed again (no 3s lockout)."""
        conn = _conn()
        for _ in range(20):
            await limiter.check_rate_limit(conn, "ep")
        blocked, _ = await limiter.check_rate_limit(conn, "ep")
        assert blocked is False
        await asyncio.sleep(0.5)  # refill ~5 tokens at 10/s
        allowed, _ = await limiter.check_rate_limit(conn, "ep")
        assert allowed is True

    async def test_different_users_separate_buckets(self, limiter):
        c1, c2 = _conn("u1"), _conn("u2")
        for _ in range(20):
            await limiter.check_rate_limit(c1, "ep")
        allowed, _ = await limiter.check_rate_limit(c2, "ep")
        assert allowed is True

    async def test_anonymous_connection_not_limited(self, limiter):
        conn = _conn(user_id=None)
        for _ in range(50):
            allowed, _ = await limiter.check_rate_limit(conn, "ep")
            assert allowed is True
        assert limiter.get_stats()["active_clients"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
class TestModes:
    async def test_off_touches_no_state(self):
        if RateLimiter is None:
            pytest.skip("Module not available")
        rl = RateLimiter(RateLimitConfig(requests_per_window=1, window_seconds=60, burst_size=0, mode="off"))
        conn = _conn()
        for _ in range(100):
            allowed, _ = await rl.check_rate_limit(conn, "ep")
            assert allowed is True
        assert rl.get_stats()["active_clients"] == 0

    async def test_monitor_mirrors_enforce_without_blocking(self):
        if RateLimiter is None:
            pytest.skip("Module not available")
        rl = RateLimiter(RateLimitConfig(requests_per_window=5, window_seconds=1, burst_size=0, mode="monitor"))
        conn = _conn()
        # max_tokens = 5; exhaust then keep going — monitor never blocks but counts would-block
        results = [await rl.check_rate_limit(conn, "ep") for _ in range(12)]
        assert all(allowed for allowed, _ in results)  # never blocked in monitor
        stats = rl.get_stats()
        assert stats["total_would_block_seen"] > 0
        assert stats["would_block_by_endpoint"].get("ep", 0) > 0


@pytest.mark.unit
class TestStatsAndReset:
    def test_get_stats_shape(self):
        if RateLimiter is None:
            pytest.skip("Module not available")
        stats = RateLimiter(RateLimitConfig(mode="enforce")).get_stats()
        for key in ("mode", "enabled", "active_clients", "total_requests_seen",
                    "total_would_block_seen", "would_block_by_endpoint", "config"):
            assert key in stats

    def test_reconfigure_preserves_state(self):
        if RateLimiter is None:
            pytest.skip("Module not available")
        rl = RateLimiter(RateLimitConfig(requests_per_window=10, window_seconds=1, burst_size=5, mode="enforce"))
        rl._total_requests_seen = 7
        rl._clients["user_x"] = ClientState()
        before = len(rl._clients)
        rl.reconfigure(RateLimitConfig(requests_per_window=100, window_seconds=1, burst_size=10, mode="monitor"))
        assert rl.config.mode == "monitor"
        assert rl._max_tokens == 110  # recomputed
        assert rl._total_requests_seen == 7  # counters preserved
        assert len(rl._clients) == before  # client state preserved


@pytest.mark.unit
@pytest.mark.asyncio
class TestLimitDecorator:
    def _handler(self):
        async def h(hass, connection, msg):
            connection.send_result(msg["id"], {"success": True})
            return "ran"
        return h

    def _hass(self, limiter):
        hass = MagicMock()
        hass.data = {DOMAIN: {"rate_limiter": limiter}} if limiter is not None else {DOMAIN: {}}
        return hass

    async def test_decorator_is_coroutine(self):
        if limit is None:
            pytest.skip("Module not available")
        wrapped = limit("ep")(self._handler())
        assert asyncio.iscoroutinefunction(wrapped)

    async def test_late_binding_enforce_blocks_with_rate_limited_result(self):
        if limit is None:
            pytest.skip("Module not available")
        rl = RateLimiter(RateLimitConfig(requests_per_window=2, window_seconds=60, burst_size=0, mode="enforce"))
        hass = self._hass(rl)
        wrapped = limit("ep")(self._handler())
        conn = _conn()
        # max_tokens = 2 -> first 2 pass, then blocked
        for _ in range(2):
            await wrapped(hass, conn, {"id": 1})
        conn.send_result.reset_mock()
        await wrapped(hass, conn, {"id": 9})
        # blocked: send_result called with rate_limited True, inner handler NOT run (no success True)
        args = conn.send_result.call_args[0]
        assert args[1].get("rate_limited") is True
        assert args[1].get("success") is False

    async def test_fail_open_when_check_raises(self):
        if limit is None:
            pytest.skip("Module not available")
        rl = RateLimiter(RateLimitConfig(mode="enforce"))
        async def boom(connection, endpoint):
            raise RuntimeError("limiter bug")
        rl.check_rate_limit = boom  # type: ignore
        hass = self._hass(rl)
        wrapped = limit("ep")(self._handler())
        conn = _conn()
        await wrapped(hass, conn, {"id": 1})
        # fail-open: inner handler ran -> success True result
        assert conn.send_result.call_args[0][1].get("success") is True

    async def test_fail_open_when_no_limiter(self):
        if limit is None:
            pytest.skip("Module not available")
        hass = self._hass(None)
        wrapped = limit("ep")(self._handler())
        conn = _conn()
        await wrapped(hass, conn, {"id": 1})
        assert conn.send_result.call_args[0][1].get("success") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
