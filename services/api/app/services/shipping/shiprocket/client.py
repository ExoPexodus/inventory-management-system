"""Shiprocket HTTP client with Redis-cached auth token (~9-day TTL)."""
from __future__ import annotations

import logging
from uuid import UUID

import httpx

from app.services.email_service import decrypt_secret
from app.worker.queue import redis_conn

logger = logging.getLogger(__name__)

BASE_URL = "https://apiv2.shiprocket.in/v1/external"
TOKEN_TTL_SECONDS = 9 * 24 * 3600  # 9 days


def _cache_key(channel_id: UUID) -> str:
    return f"shiprocket:token:{channel_id}"


def invalidate_token(channel_id: UUID) -> None:
    redis_conn().delete(_cache_key(channel_id))


def get_token(channel_id: UUID, config: dict) -> str:
    r = redis_conn()
    cached = r.get(_cache_key(channel_id))
    if cached:
        return cached.decode("utf-8") if isinstance(cached, bytes) else str(cached)

    email = config.get("shiprocket_email", "")
    password = decrypt_secret(config.get("shiprocket_password", "")) or ""
    if not email or not password:
        raise ValueError("Shiprocket credentials not configured on this channel")

    resp = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
        timeout=15.0,
    )
    resp.raise_for_status()
    token = resp.json()["token"]
    r.setex(_cache_key(channel_id), TOKEN_TTL_SECONDS, token)
    return token


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def api_post(channel_id: UUID, config: dict, path: str, payload: dict) -> dict:
    """Authenticated POST, retries once on 401 (refreshes token)."""
    token = get_token(channel_id, config)
    resp = httpx.post(f"{BASE_URL}{path}", json=payload,
                      headers=_auth_headers(token), timeout=30.0)
    if resp.status_code == 401:
        invalidate_token(channel_id)
        token = get_token(channel_id, config)
        resp = httpx.post(f"{BASE_URL}{path}", json=payload,
                          headers=_auth_headers(token), timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def api_get(channel_id: UUID, config: dict, path: str) -> dict:
    """Authenticated GET, retries once on 401."""
    token = get_token(channel_id, config)
    resp = httpx.get(f"{BASE_URL}{path}", headers=_auth_headers(token), timeout=15.0)
    if resp.status_code == 401:
        invalidate_token(channel_id)
        token = get_token(channel_id, config)
        resp = httpx.get(f"{BASE_URL}{path}", headers=_auth_headers(token), timeout=15.0)
    resp.raise_for_status()
    return resp.json()
