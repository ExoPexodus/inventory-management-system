"""Per-channel CORS Origin allowlist enforcement for /v1/storefront/* paths.

Channel.config.allowed_origins is a list of HTTPS URLs. When set, requests
to storefront endpoints with an Origin header that doesn't match are
rejected with 403. Requests without an Origin header (server-to-server)
are allowed through — the CORS allowlist is a browser-only defense.

When allowed_origins is empty or missing, the channel keeps current behavior
(no Origin restriction).

Fails open on DB/Redis errors so a misconfiguration doesn't black-hole the
storefront.
"""
from __future__ import annotations

import logging
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

STOREFRONT_PREFIX = "/v1/storefront"


class StorefrontOriginCheckMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not request.url.path.startswith(STOREFRONT_PREFIX):
            return await call_next(request)

        origin = request.headers.get("origin") or request.headers.get("Origin")
        if not origin:
            # Server-to-server — pass through
            return await call_next(request)

        channel_id_str = (
            request.headers.get("x-channel-id")
            or request.headers.get("X-Channel-Id")
        )
        if not channel_id_str:
            # Channel resolver downstream will 4xx for this case
            return await call_next(request)

        try:
            channel_id = UUID(channel_id_str)
            from app.db.session import SessionLocal
            from app.models import Channel

            db = SessionLocal()
            try:
                channel = db.get(Channel, channel_id)
            finally:
                db.close()

            if channel is None:
                return await call_next(request)  # downstream will 404

            allowed = (channel.config or {}).get("allowed_origins") or []
            if allowed and origin not in allowed:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Origin not allowed for this channel"},
                )

            # Fall through; downstream handler runs
            response = await call_next(request)

            # Reflect the matched Origin so the browser accepts the response.
            if allowed:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Vary"] = "Origin"
            return response
        except Exception:
            logger.debug("Origin check failed; failing open", exc_info=True)
            return await call_next(request)
