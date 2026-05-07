"""Per-IP rate limiting for /v1/storefront/* paths.

Uses Redis INCR + EXPIRE for a fixed 60-second tumbling window.
Fails open (allows request) if Redis is unavailable.
Admin, device, and health routes are never rate-limited.
"""
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

STOREFRONT_PREFIX = "/v1/storefront"
LIMIT = 120    # max requests per window
WINDOW = 60    # seconds


class StorefrontRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not request.url.path.startswith(STOREFRONT_PREFIX):
            return await call_next(request)

        client_ip = (request.client.host if request.client else None) or "unknown"
        key = f"rl:storefront:{client_ip}"

        try:
            from app.config import settings
            import redis.asyncio as aioredis

            r: aioredis.Redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            async with r:
                count = await r.incr(key)
                if count == 1:
                    # Only set TTL on the first increment — fixed tumbling window
                    await r.expire(key, WINDOW)
                if count > LIMIT:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests. Please slow down."},
                        headers={"Retry-After": str(WINDOW)},
                    )
        except Exception:
            logger.debug("Rate limiter Redis unavailable, failing open", exc_info=True)

        return await call_next(request)
