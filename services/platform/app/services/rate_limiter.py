"""Simple in-memory rate limiter for public endpoints.

Uses a sliding window approach with per-IP tracking.
In production with multiple workers, swap for a Redis-backed implementation.
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self._max = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.time()
        cutoff = now - self._window

        with self._lock:
            timestamps = self._requests[key]
            # Remove expired entries
            self._requests[key] = [t for t in timestamps if t > cutoff]
            timestamps = self._requests[key]

            if len(timestamps) >= self._max:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later.",
                )
            timestamps.append(now)

    def cleanup(self) -> int:
        """Remove stale entries. Call periodically to prevent memory growth."""
        now = time.time()
        cutoff = now - self._window
        removed = 0
        with self._lock:
            stale_keys = [k for k, v in self._requests.items() if all(t <= cutoff for t in v)]
            for k in stale_keys:
                del self._requests[k]
                removed += 1
        return removed


# Global instances for public endpoints
# Download page: 30 requests per minute per IP
download_page_limiter = RateLimiter(max_requests=30, window_seconds=60)
# File download: 10 requests per minute per IP (files are large)
file_download_limiter = RateLimiter(max_requests=10, window_seconds=60)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
