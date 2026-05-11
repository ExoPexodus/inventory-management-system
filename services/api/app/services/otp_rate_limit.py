"""Per-email OTP / magic-link rate limit.

Backed by Redis with two windows:
  - 5 requests per hour
  - 30 requests per day

Keyed by (channel_id, sha256(email_lower)[:16]). Fails open on Redis errors.
"""
from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from fastapi import HTTPException

logger = logging.getLogger(__name__)

HOURLY_LIMIT = 5
HOURLY_WINDOW = 3600
DAILY_LIMIT = 30
DAILY_WINDOW = 86400


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()[:16]


def check_otp_rate_limit(email: str, channel_id: UUID) -> None:
    """Raise HTTPException(429) if the per-email OTP limit is breached.

    Uses the synchronous Redis client — call from regular ``def`` handlers.
    Fails open on Redis errors so a Redis outage never blocks OTP delivery.
    """
    try:
        from app.config import settings
        import redis as sync_redis

        eh = _email_hash(email)
        hr_key = f"rl:otp:{channel_id}:{eh}:hr"
        day_key = f"rl:otp:{channel_id}:{eh}:day"

        client = sync_redis.from_url(settings.redis_url, decode_responses=True)
        try:
            hr_count = client.incr(hr_key)
            if hr_count == 1:
                client.expire(hr_key, HOURLY_WINDOW)
            day_count = client.incr(day_key)
            if day_count == 1:
                client.expire(day_key, DAILY_WINDOW)
            if hr_count > HOURLY_LIMIT or day_count > DAILY_LIMIT:
                raise HTTPException(
                    status_code=429,
                    detail="Too many verification code requests. Try again later.",
                    headers={"Retry-After": "3600"},
                )
        finally:
            client.close()
    except HTTPException:
        raise
    except Exception:
        logger.debug("OTP rate limiter unavailable, failing open", exc_info=True)
