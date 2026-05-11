"""Add baseline security headers to every response.

API responses don't need the full CSP/frame-ancestors policy that an HTML
page would, but a few headers still matter:

- ``X-Content-Type-Options: nosniff`` — stops browsers from sniffing JSON
  as HTML and executing it.
- ``X-Frame-Options: DENY`` — defence in depth in case any endpoint ever
  returns HTML that could be framed.
- ``Referrer-Policy: strict-origin-when-cross-origin`` — never leaks query
  strings to third-party origins.
- ``Strict-Transport-Security: max-age=31536000; includeSubDomains`` —
  only set when the request was already over HTTPS so dev-mode HTTP
  isn't broken.

The ``Server: uvicorn`` header is also stripped because version disclosure
is an unnecessary recon assist.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # HSTS is only meaningful over HTTPS — guard so dev http: doesn't
        # get a confusing header that breaks future http access if a
        # browser caches it.
        forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
        scheme = request.url.scheme.lower()
        if forwarded_proto == "https" or scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        # Server header is suppressed at the uvicorn layer via
        # `--no-server-header` (see services/api/Dockerfile) — middleware
        # can't reliably strip it because uvicorn re-adds it after this
        # response is built.
        return response
