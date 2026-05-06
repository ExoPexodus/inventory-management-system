"""Engineering rollout flags — separate from plan entitlements.

Flags answer "is this feature rolled out yet?", entitlements answer "does this
plan include it?". Layer in code as ``ents.require(...)`` THEN
``flags.is_enabled(...)`` — a 403 (commercial) takes precedence over a 503
(rollout).

Rules format::

    {
      "allowlist": ["<tenant-uuid>", ...],
      "denylist": ["<tenant-uuid>", ...],
      "percent":  0..100
    }

Resolution: an allowlist match forces ON, denylist match forces OFF, otherwise
the bucket from a stable hash of (tenant_id, flag_key) decides percent rollout,
falling back to ``default_state``.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FeatureFlag
from app.worker.queue import redis_conn

logger = logging.getLogger(__name__)

CACHE_PREFIX = "flag:v1"
CACHE_TTL_SECONDS = 60  # short — flags change during rollouts


def _bucket(tenant_id: UUID, flag_key: str) -> int:
    """Stable 0..99 bucket. Same tenant + same flag = same bucket."""
    h = hashlib.sha1(f"{tenant_id}:{flag_key}".encode()).digest()
    return h[0] % 100


def _eval_rules(tenant_id: UUID, flag: FeatureFlag) -> bool:
    rules: dict[str, Any] = flag.rollout_rules or {}
    tid = str(tenant_id)

    if tid in (rules.get("denylist") or []):
        return False
    if tid in (rules.get("allowlist") or []):
        return True

    pct = rules.get("percent")
    if isinstance(pct, int) and 0 <= pct <= 100:
        if pct == 100:
            return True  # short-circuit: skip the hash for full rollout
        if _bucket(tenant_id, flag.key) < pct:
            return True
        # Below percent threshold: fall through to default_state
        # (matters when default_state=True and percent is acting as a denylist gate)
    return flag.default_state


def is_enabled(db: Session, tenant_id: UUID, flag_key: str) -> bool:
    """Return True if the flag is enabled for the tenant."""
    cached = _read_cache(flag_key)
    if cached is not None:
        flag = cached
    else:
        flag = db.execute(
            select(FeatureFlag).where(FeatureFlag.key == flag_key)
        ).scalar_one_or_none()
        if flag is None:
            return False
        _write_cache(flag)

    return _eval_rules(tenant_id, flag)


def invalidate_flag_cache(flag_key: str) -> None:
    try:
        redis_conn().delete(f"{CACHE_PREFIX}:{flag_key}")
    except Exception:
        logger.warning("Failed to invalidate flag cache for %s", flag_key, exc_info=True)


def _read_cache(flag_key: str) -> FeatureFlag | None:
    try:
        raw = redis_conn().get(f"{CACHE_PREFIX}:{flag_key}")
        if raw is None:
            return None
        payload = json.loads(raw)
        # Construct a transient FeatureFlag (not attached to session) for evaluation
        f = FeatureFlag()
        f.key = payload["key"]
        f.default_state = payload["default_state"]
        f.rollout_rules = payload.get("rollout_rules")
        return f
    except Exception:
        logger.warning("Flag cache read failed for %s", flag_key, exc_info=True)
        return None


def _write_cache(flag: FeatureFlag) -> None:
    try:
        payload = json.dumps({
            "key": flag.key,
            "default_state": flag.default_state,
            "rollout_rules": flag.rollout_rules,
        })
        redis_conn().setex(f"{CACHE_PREFIX}:{flag.key}", CACHE_TTL_SECONDS, payload)
    except Exception:
        logger.warning("Flag cache write failed for %s", flag.key, exc_info=True)
