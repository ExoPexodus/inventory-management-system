"""Tests for the per-email OTP / magic-link rate limiter."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.otp_rate_limit import (
    DAILY_LIMIT,
    HOURLY_LIMIT,
    check_otp_rate_limit,
)

_CHANNEL_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
_EMAIL = "test@example.com"


def _make_redis_mock(hr_count: int, day_count: int) -> MagicMock:
    """Build a sync Redis mock whose incr() returns hr_count for the first call,
    then day_count for the second call."""
    client = MagicMock()
    client.incr = MagicMock(side_effect=[hr_count, day_count])
    client.expire = MagicMock(return_value=True)
    client.close = MagicMock()
    return client


def test_under_hourly_limit_passes() -> None:
    """Requests under the hourly limit go through silently."""
    mock_redis = _make_redis_mock(hr_count=1, day_count=1)
    with patch("redis.from_url", return_value=mock_redis):
        # Should not raise
        check_otp_rate_limit(email=_EMAIL, channel_id=_CHANNEL_ID)


def test_at_hourly_limit_passes() -> None:
    """The 5th request in an hour is still allowed."""
    mock_redis = _make_redis_mock(hr_count=HOURLY_LIMIT, day_count=HOURLY_LIMIT)
    with patch("redis.from_url", return_value=mock_redis):
        check_otp_rate_limit(email=_EMAIL, channel_id=_CHANNEL_ID)


def test_exceeds_hourly_limit_raises_429() -> None:
    """The 6th request in an hour raises 429."""
    mock_redis = _make_redis_mock(hr_count=HOURLY_LIMIT + 1, day_count=1)
    with patch("redis.from_url", return_value=mock_redis):
        with pytest.raises(HTTPException) as exc_info:
            check_otp_rate_limit(email=_EMAIL, channel_id=_CHANNEL_ID)
    assert exc_info.value.status_code == 429
    assert "Too many verification code requests" in exc_info.value.detail


def test_exceeds_daily_limit_raises_429() -> None:
    """Exceeding the daily limit raises 429 even if hourly count is within range."""
    mock_redis = _make_redis_mock(hr_count=1, day_count=DAILY_LIMIT + 1)
    with patch("redis.from_url", return_value=mock_redis):
        with pytest.raises(HTTPException) as exc_info:
            check_otp_rate_limit(email=_EMAIL, channel_id=_CHANNEL_ID)
    assert exc_info.value.status_code == 429


def test_redis_error_fails_open() -> None:
    """If Redis raises, the limiter fails open (no exception propagated)."""
    with patch("redis.from_url", side_effect=Exception("Redis down")):
        # Should not raise anything
        check_otp_rate_limit(email=_EMAIL, channel_id=_CHANNEL_ID)


def test_expire_called_only_on_first_increment() -> None:
    """TTL is only set when count == 1 for each key."""
    mock_redis = _make_redis_mock(hr_count=2, day_count=2)
    with patch("redis.from_url", return_value=mock_redis):
        check_otp_rate_limit(email=_EMAIL, channel_id=_CHANNEL_ID)
    # Neither counter hit 1, so expire should not have been called
    mock_redis.expire.assert_not_called()


def test_expire_called_for_new_key() -> None:
    """TTL is set when a key is created for the first time (count == 1)."""
    mock_redis = _make_redis_mock(hr_count=1, day_count=1)
    with patch("redis.from_url", return_value=mock_redis):
        check_otp_rate_limit(email=_EMAIL, channel_id=_CHANNEL_ID)
    assert mock_redis.expire.call_count == 2  # once for hr_key, once for day_key


def test_different_emails_use_different_keys() -> None:
    """Two different emails produce different Redis keys."""
    calls: list[str] = []

    def capture_incr(key: str) -> int:
        calls.append(key)
        return 1

    mock_redis = MagicMock()
    mock_redis.incr = MagicMock(side_effect=capture_incr)
    mock_redis.expire = MagicMock(return_value=True)
    mock_redis.close = MagicMock()

    with patch("redis.from_url", return_value=mock_redis):
        check_otp_rate_limit(email="alice@example.com", channel_id=_CHANNEL_ID)
        check_otp_rate_limit(email="bob@example.com", channel_id=_CHANNEL_ID)

    # All 4 keys should be distinct
    assert len(set(calls)) == 4
