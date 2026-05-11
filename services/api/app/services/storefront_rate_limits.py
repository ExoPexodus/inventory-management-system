"""Storefront-specific rate limits beyond the global per-IP limiter.

Three helpers, all Redis-backed and failing open on infrastructure errors:

- ``record_discount_attempt(ip, channel_id, success)`` — counts FAILED discount
  code submissions per IP per channel. After 5 failures in 10 minutes the
  endpoint should return 429 to slow down code enumeration.

- ``check_cart_creation_rate(ip, channel_id)`` — caps cart creation at
  20/min and 200/hour per IP per channel to bound DB spam from script
  abuse.

- ``check_discount_rate_limit(ip, channel_id)`` — guard called before the
  discount lookup; raises 429 if the IP has already burned its discount
  failure budget.

Keys are scoped by both IP and channel_id so noisy neighbours on shared
NAT exits don't starve a quiet tenant.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Discount-attempt limits
DISCOUNT_FAIL_LIMIT = 5
DISCOUNT_FAIL_WINDOW = 600  # 10 minutes

# Cart-create limits
CART_CREATE_MINUTE_LIMIT = 20
CART_CREATE_MINUTE_WINDOW = 60
CART_CREATE_HOURLY_LIMIT = 200
CART_CREATE_HOURLY_WINDOW = 3600


def _redis_client():
    from app.config import settings
    import redis as sync_redis
    return sync_redis.from_url(settings.redis_url, decode_responses=True)


def check_discount_rate_limit(ip: str, channel_id: UUID) -> None:
    """Raise 429 if this IP has burned its discount-failure budget.

    Call this BEFORE looking up the discount. Combined with
    ``record_discount_attempt`` below, this blocks code enumeration: each
    invalid attempt counts, and once the counter hits the limit no further
    attempts (valid OR invalid) are evaluated until the window expires.
    """
    try:
        key = f"rl:discount_fail:{channel_id}:{ip}"
        client = _redis_client()
        try:
            count_raw = client.get(key)
            count = int(count_raw) if count_raw else 0
            if count >= DISCOUNT_FAIL_LIMIT:
                ttl = client.ttl(key)
                retry = ttl if ttl and ttl > 0 else DISCOUNT_FAIL_WINDOW
                raise HTTPException(
                    status_code=429,
                    detail="Too many discount code attempts. Try again later.",
                    headers={"Retry-After": str(retry)},
                )
        finally:
            client.close()
    except HTTPException:
        raise
    except Exception:
        logger.debug("Discount rate limiter unavailable, failing open", exc_info=True)


def record_discount_attempt(ip: str, channel_id: UUID, success: bool) -> None:
    """Record the outcome of a discount lookup.

    Successful attempts clear the counter (a real customer who got their
    code right shouldn't be penalised for a few typos). Failed attempts
    increment it and refresh the TTL.
    """
    try:
        key = f"rl:discount_fail:{channel_id}:{ip}"
        client = _redis_client()
        try:
            if success:
                client.delete(key)
            else:
                count = client.incr(key)
                if count == 1:
                    client.expire(key, DISCOUNT_FAIL_WINDOW)
        finally:
            client.close()
    except Exception:
        logger.debug("Discount rate limiter unavailable, failing open", exc_info=True)


def check_cart_creation_rate(ip: str, channel_id: UUID) -> None:
    """Raise 429 if this IP is creating carts too fast.

    Two windows so a burst doesn't immediately lock the IP for an hour
    but sustained spam does.
    """
    try:
        min_key = f"rl:cart_create:{channel_id}:{ip}:min"
        hr_key = f"rl:cart_create:{channel_id}:{ip}:hr"
        client = _redis_client()
        try:
            mc = client.incr(min_key)
            if mc == 1:
                client.expire(min_key, CART_CREATE_MINUTE_WINDOW)
            hc = client.incr(hr_key)
            if hc == 1:
                client.expire(hr_key, CART_CREATE_HOURLY_WINDOW)
            if mc > CART_CREATE_MINUTE_LIMIT or hc > CART_CREATE_HOURLY_LIMIT:
                ttl = max(client.ttl(min_key) or 0, 60)
                raise HTTPException(
                    status_code=429,
                    detail="Too many cart creations. Try again later.",
                    headers={"Retry-After": str(ttl)},
                )
        finally:
            client.close()
    except HTTPException:
        raise
    except Exception:
        logger.debug("Cart-create rate limiter unavailable, failing open", exc_info=True)
