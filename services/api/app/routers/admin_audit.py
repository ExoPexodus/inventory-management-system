"""Admin audit log endpoint — immutable trail of operator actions."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.db.admin_deps_db import get_db_admin
from app.models import AdminAuditLog, AdminUser

router = APIRouter(prefix="/v1/admin/audit-log", tags=["Admin Audit"])


class AuditEventOut(BaseModel):
    id: UUID
    actor: str
    action: str
    resource_type: str
    resource_id: str | None
    ip_address: str | None
    created_at: str


class AuditListResponse(BaseModel):
    items: list[AuditEventOut]
    next_cursor: str | None


@router.get("", response_model=AuditListResponse)
def list_audit_log(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    q: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    after: str | None = Query(default=None),  # cursor: id of last seen record
    limit: int = Query(default=50, ge=1, le=100),
) -> AuditListResponse:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant-scoped operator required")

    tenant_id = ctx.tenant_id

    stmt = (
        select(AdminAuditLog)
        .where(AdminAuditLog.tenant_id == tenant_id)
        .order_by(AdminAuditLog.created_at.desc())
        .limit(limit + 1)
    )

    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            AdminAuditLog.action.ilike(pattern)
            | AdminAuditLog.resource_type.ilike(pattern)
            | AdminAuditLog.resource_id.ilike(pattern)
        )

    if from_date:
        stmt = stmt.where(AdminAuditLog.created_at >= from_date)
    if to_date:
        stmt = stmt.where(AdminAuditLog.created_at <= to_date + "T23:59:59")

    if after:
        try:
            after_uuid = UUID(after)
            cursor_row = db.get(AdminAuditLog, after_uuid)
            if cursor_row and cursor_row.tenant_id == tenant_id:
                stmt = stmt.where(AdminAuditLog.created_at < cursor_row.created_at)
        except (ValueError, AttributeError):
            pass

    rows = db.execute(stmt).scalars().all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    # Resolve operator emails in one query
    op_ids = {r.operator_id for r in rows if r.operator_id}
    op_emails: dict[UUID, str] = {}
    if op_ids:
        ops = db.execute(select(AdminUser).where(AdminUser.id.in_(op_ids))).scalars().all()
        op_emails = {o.id: o.email for o in ops}

    items = [
        AuditEventOut(
            id=r.id,
            actor=op_emails.get(r.operator_id, "system") if r.operator_id else "system",
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            ip_address=r.ip_address,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]

    next_cursor = str(rows[-1].id) if has_more and rows else None

    return AuditListResponse(items=items, next_cursor=next_cursor)
