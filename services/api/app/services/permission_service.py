"""Cached permission lookup for RBAC.

Keeps an in-process dict of role_id → frozenset[codename] with a 60-second TTL.
Call invalidate_role_cache(role_id) after any mutation to role_permissions so the
next request picks up the change immediately.
"""

from __future__ import annotations

import time
import uuid
from typing import NamedTuple

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.tables import Permission, RolePermission

_TTL_SECONDS = 60


class _CacheEntry(NamedTuple):
    permissions: frozenset[str]
    expires_at: float


_cache: dict[uuid.UUID, _CacheEntry] = {}


def get_role_permissions(db: Session, role_id: uuid.UUID) -> frozenset[str]:
    """Return cached set of permission codenames for *role_id*. 60-second TTL."""
    now = time.monotonic()
    entry = _cache.get(role_id)
    if entry and entry.expires_at > now:
        return entry.permissions

    rows = (
        db.execute(
            sa.select(Permission.codename)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        .scalars()
        .all()
    )
    perms = frozenset(rows)
    _cache[role_id] = _CacheEntry(permissions=perms, expires_at=now + _TTL_SECONDS)
    return perms


def invalidate_role_cache(role_id: uuid.UUID) -> None:
    """Remove *role_id* from the cache so the next request hits the DB."""
    _cache.pop(role_id, None)
