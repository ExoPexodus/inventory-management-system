"""Fetches the feature catalog from the IMS service so plan operators can
validate feature_keys against a known set when editing plan features.

The catalog is cached for 5 minutes since it changes only when IMS deploys.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] | None = None
_CACHE_EXPIRES: float = 0
_TTL_SECONDS = 300


def get_feature_catalog() -> dict[str, dict]:
    """Returns {feature_key: {value_type, default, description}} from IMS.

    Falls back to an empty dict if IMS is unreachable — calls to validate
    against an unknown key in that case become best-effort (accept).
    """
    global _CACHE, _CACHE_EXPIRES
    now = time.time()
    if _CACHE is not None and now < _CACHE_EXPIRES:
        return _CACHE

    try:
        url = f"{settings.main_api_url}/v1/internal/platform/plan-features"
        resp = httpx.get(url, timeout=5.0, headers={"X-Admin-Token": settings.admin_api_token})
        if resp.status_code == 200:
            data = resp.json()
            _CACHE = {item["key"]: item for item in data}
            _CACHE_EXPIRES = now + _TTL_SECONDS
            return _CACHE
    except Exception:
        logger.warning("Failed to fetch feature catalog from IMS", exc_info=True)
    return _CACHE or {}
