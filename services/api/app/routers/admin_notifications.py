"""Admin notifications endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, AdminContext, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Notification

router = APIRouter(prefix="/v1/admin/notifications", tags=["Admin Notifications"])


class NotificationOut(BaseModel):
    id: UUID
    type: str
    title: str
    body: str | None
    resource_type: str | None
    resource_id: str | None
    read_at: str | None
    created_at: str


class NotificationsResponse(BaseModel):
    items: list[NotificationOut]
    unread_count: int


def _to_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        type=n.type,
        title=n.title,
        body=n.body,
        resource_type=n.resource_type,
        resource_id=n.resource_id,
        read_at=n.read_at.isoformat() if n.read_at else None,
        created_at=n.created_at.isoformat(),
    )


@router.get("", response_model=NotificationsResponse, dependencies=[require_permission("notifications:read")])
def list_notifications(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    unread_only: bool = Query(default=False),
) -> NotificationsResponse:
    from app.auth.admin_deps import AdminContext as _Ctx  # noqa: F401
    tenant_id = ctx.tenant_id
    if tenant_id is None:
        return NotificationsResponse(items=[], unread_count=0)

    stmt = (
        select(Notification)
        .where(Notification.tenant_id == tenant_id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))

    items = db.execute(stmt).scalars().all()

    unread_count = sum(1 for n in items if n.read_at is None)
    if not unread_only:
        # count all unread (items may be limited to 50)
        from sqlalchemy import func
        unread_count = db.execute(
            select(func.count(Notification.id)).where(
                Notification.tenant_id == tenant_id,
                Notification.read_at.is_(None),
            )
        ).scalar_one()

    return NotificationsResponse(
        items=[_to_out(n) for n in items],
        unread_count=unread_count,
    )


@router.patch("/{notification_id}/read", response_model=NotificationOut, dependencies=[require_permission("notifications:write")])
def mark_read(
    notification_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> NotificationOut:
    from fastapi import HTTPException, status
    tenant_id = ctx.tenant_id
    n = db.get(Notification, notification_id)
    if n is None or n.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
        db.commit()
        db.refresh(n)
    return _to_out(n)


@router.post("/read-all", dependencies=[require_permission("notifications:write")])
def mark_all_read(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict:
    tenant_id = ctx.tenant_id
    if tenant_id is None:
        return {"updated": 0}
    now = datetime.now(UTC)
    result = db.execute(
        update(Notification)
        .where(Notification.tenant_id == tenant_id, Notification.read_at.is_(None))
        .values(read_at=now)
    )
    db.commit()
    return {"updated": result.rowcount}
