"""Tests for storefront rate limiting middleware."""
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app


def test_storefront_request_allowed_when_under_limit() -> None:
    """Requests under the limit pass through (return non-429)."""
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    mock_pipe.execute.return_value = [1, True]  # count=1, expire result

    with patch("app.middleware.storefront_rate_limit.redis_conn", return_value=mock_redis):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/v1/storefront/products",
            headers={"X-Channel-Id": "00000000-0000-0000-0000-000000000001"},
        )
    # Should not be 429 (may be 404/422 since no real channel, but not rate-limited)
    assert resp.status_code != 429


def test_storefront_request_blocked_when_over_limit() -> None:
    """Returns 429 when Redis counter exceeds LIMIT."""
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    mock_pipe.execute.return_value = [121, True]  # count=121 > LIMIT=120

    with patch("app.middleware.storefront_rate_limit.redis_conn", return_value=mock_redis):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/v1/storefront/products",
            headers={"X-Channel-Id": "00000000-0000-0000-0000-000000000001"},
        )
    assert resp.status_code == 429
    assert "Too many requests" in resp.json()["detail"]


def test_admin_route_never_rate_limited() -> None:
    """Admin routes bypass rate limiting entirely — Redis is never called."""
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    mock_pipe.execute.return_value = [9999, True]  # very high count

    with patch("app.middleware.storefront_rate_limit.redis_conn", return_value=mock_redis):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/v1/admin/channels")
    # Should never be 429 regardless of Redis counter
    assert resp.status_code != 429
    mock_pipe.execute.assert_not_called()


def test_rate_limiter_fails_open_when_redis_unavailable() -> None:
    """If Redis throws, the request is allowed through (fail-open)."""
    with patch("app.middleware.storefront_rate_limit.redis_conn", side_effect=Exception("Redis down")):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/v1/storefront/products",
            headers={"X-Channel-Id": "00000000-0000-0000-0000-000000000001"},
        )
    assert resp.status_code != 429
