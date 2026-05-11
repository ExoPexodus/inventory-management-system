"""Tests for the discount-enumeration and cart-creation rate limiters."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.storefront_rate_limits import (
    CART_CREATE_HOURLY_LIMIT,
    CART_CREATE_MINUTE_LIMIT,
    DISCOUNT_FAIL_LIMIT,
    check_cart_creation_rate,
    check_discount_rate_limit,
    record_discount_attempt,
)


def _mock_redis(counter_returns: list[int] | None = None,
                ttl_return: int | None = None,
                get_return: str | None = None):
    """Return a mock redis client whose incr() walks through counter_returns."""
    client = MagicMock()
    if counter_returns is not None:
        client.incr.side_effect = counter_returns
    client.expire.return_value = True
    client.ttl.return_value = ttl_return if ttl_return is not None else 600
    client.get.return_value = get_return
    client.delete.return_value = 1
    return client


# ──────────────────── discount enumeration ────────────────────

def test_discount_rate_limit_passes_when_under_limit() -> None:
    client = _mock_redis(get_return=str(DISCOUNT_FAIL_LIMIT - 1))
    with patch("app.services.storefront_rate_limits._redis_client", return_value=client):
        # Should not raise — under the failure budget
        check_discount_rate_limit("1.2.3.4", uuid4())


def test_discount_rate_limit_raises_429_when_over() -> None:
    client = _mock_redis(get_return=str(DISCOUNT_FAIL_LIMIT))
    with patch("app.services.storefront_rate_limits._redis_client", return_value=client):
        with pytest.raises(HTTPException) as exc_info:
            check_discount_rate_limit("1.2.3.4", uuid4())
    assert exc_info.value.status_code == 429
    assert "discount code" in exc_info.value.detail.lower()


def test_discount_rate_limit_fails_open_on_redis_error() -> None:
    with patch("app.services.storefront_rate_limits._redis_client",
               side_effect=Exception("Redis down")):
        # Should silently allow the request through
        check_discount_rate_limit("1.2.3.4", uuid4())


def test_record_discount_attempt_increments_on_failure() -> None:
    client = _mock_redis(counter_returns=[1])
    with patch("app.services.storefront_rate_limits._redis_client", return_value=client):
        record_discount_attempt("1.2.3.4", uuid4(), success=False)
    client.incr.assert_called_once()
    client.expire.assert_called_once()


def test_record_discount_attempt_clears_on_success() -> None:
    client = _mock_redis()
    with patch("app.services.storefront_rate_limits._redis_client", return_value=client):
        record_discount_attempt("1.2.3.4", uuid4(), success=True)
    client.delete.assert_called_once()
    client.incr.assert_not_called()


# ──────────────────── cart creation ────────────────────

def test_cart_creation_under_limit_passes() -> None:
    client = _mock_redis(counter_returns=[1, 1])
    with patch("app.services.storefront_rate_limits._redis_client", return_value=client):
        check_cart_creation_rate("1.2.3.4", uuid4())


def test_cart_creation_over_minute_limit_raises_429() -> None:
    client = _mock_redis(counter_returns=[CART_CREATE_MINUTE_LIMIT + 1, 1])
    with patch("app.services.storefront_rate_limits._redis_client", return_value=client):
        with pytest.raises(HTTPException) as exc_info:
            check_cart_creation_rate("1.2.3.4", uuid4())
    assert exc_info.value.status_code == 429
    assert "cart" in exc_info.value.detail.lower()


def test_cart_creation_over_hourly_limit_raises_429() -> None:
    client = _mock_redis(counter_returns=[1, CART_CREATE_HOURLY_LIMIT + 1])
    with patch("app.services.storefront_rate_limits._redis_client", return_value=client):
        with pytest.raises(HTTPException) as exc_info:
            check_cart_creation_rate("1.2.3.4", uuid4())
    assert exc_info.value.status_code == 429


def test_cart_creation_fails_open_on_redis_error() -> None:
    with patch("app.services.storefront_rate_limits._redis_client",
               side_effect=Exception("Redis down")):
        check_cart_creation_rate("1.2.3.4", uuid4())  # should not raise


def test_cart_creation_minute_ttl_set_on_first_request() -> None:
    client = _mock_redis(counter_returns=[1, 1])
    with patch("app.services.storefront_rate_limits._redis_client", return_value=client):
        check_cart_creation_rate("1.2.3.4", uuid4())
    # expire is called twice — once for minute key on first incr, once for hour
    assert client.expire.call_count == 2
