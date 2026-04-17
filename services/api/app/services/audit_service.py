"""Audit logging helper — call write_audit() inside any mutation handler."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AdminAuditLog


def write_audit(
    db: Session,
    *,
    tenant_id: UUID,
    operator_id: UUID | None = None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Append an audit record to the current session (no separate commit)."""
    log = AdminAuditLog(
        tenant_id=tenant_id,
        user_id=operator_id,  # kwarg kept as operator_id for backward-compat with callers
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        before_snapshot=before,
        after_snapshot=after,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
