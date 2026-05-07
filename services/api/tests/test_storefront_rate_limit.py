"""Tests for storefront rate limiting middleware."""
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app


def _make_redis_mock(incr_return: int) -> MagicMock:
    """Create an async context-manager mock for redis.asyncio.from_url."""
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=incr_return)
    mock_redis.expire = AsyncMock(return_value=True)
    mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
    mock_redis.__aexit__ = AsyncMock(return_value=False)
    return mock_redis


def test_storefront_request_allowed_when_under_limit() -> None:
    """Requests under the limit pass through (return non-429)."""
    mock_redis = _make_redis_mock(incr_return=1)

    with patch("redis.asyncio.from_url", return_value=mock_redis):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/v1/storefront/products",
            headers={"X-Channel-Id": "00000000-0000-0000-0000-000000000001"},
        )
    assert resp.status_code != 429


def test_storefront_request_blocked_when_over_limit() -> None:
    """Returns 429 when count exceeds LIMIT."""
    mock_redis = _make_redis_mock(incr_return=121)

    with patch("redis.asyncio.from_url", return_value=mock_redis):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/v1/storefront/products",
            headers={"X-Channel-Id": "00000000-0000-0000-0000-000000000001"},
        )
    assert resp.status_code == 429
    assert "Too many requests" in resp.json()["detail"]


def test_admin_route_never_rate_limited() -> None:
    """Admin routes bypass rate limiting entirely."""
    mock_redis = _make_redis_mock(incr_return=9999)

    with patch("redis.asyncio.from_url", return_value=mock_redis) as mock_factory:
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/v1/admin/channels")
    assert resp.status_code != 429
    mock_factory.assert_not_called()


def test_rate_limiter_fails_open_when_redis_unavailable() -> None:
    """If Redis throws, the request is allowed through (fail-open)."""
    with patch("redis.asyncio.from_url", side_effect=Exception("Redis down")):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/v1/storefront/products",
            headers={"X-Channel-Id": "00000000-0000-0000-0000-000000000001"},
        )
    assert resp.status_code != 429


def test_expire_only_called_on_first_increment() -> None:
    """TTL is set only when count == 1 (fixed tumbling window)."""
    mock_redis = _make_redis_mock(incr_return=50)  # not the first increment

    with patch("redis.asyncio.from_url", return_value=mock_redis):
        client = TestClient(app, raise_server_exceptions=False)
        client.get(
            "/v1/storefront/products",
            headers={"X-Channel-Id": "00000000-0000-0000-0000-000000000001"},
        )
    # expire should NOT be called when count > 1
    mock_redis.expire.assert_not_called()
