"""Admin endpoints for stock reservation visibility + manual ops.

Primarily a debug/support tool — normal lifecycle (reserve on cart-add, commit
on order, release on cart-clear, expire via sweeper) runs without admin
intervention. Operators inspect in-flight holds and force-release stuck rows.

Auth: requires `reservations:manage` permission. Granted to the system `owner`
role by migration 20260508000001.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import StockReservation
from app.services.reservation_service import release_reservation, sweep_expired

router = APIRouter(
    prefix="/v1/admin/reservations",
    tags=["Admin Reservations"],
    dependencies=[require_permission("reservations:manage")],
)


_ALLOWED_STATUSES = {"active", "committed", "released", "expired"}


class StockReservationOut(BaseModel):
    id: UUID
    tenant_id: UUID
    channel_id: UUID
    product_id: UUID
    shop_id: UUID
    quantity: int
    cart_token: str
    purpose: str
    status: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SweepResponse(BaseModel):
    expired_count: int


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


@router.get("", response_model=list[StockReservationOut])
def list_reservations(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[StockReservation]:
    """List reservations for the operator's tenant.

    The query param is named ``status`` in the URL (via Query alias) but kept as
    ``status_filter`` in the function signature to avoid shadowing FastAPI's
    ``status`` HTTP-status module imported above.
    """
    tenant_id = _require_tenant(ctx)
    q = select(StockReservation).where(StockReservation.tenant_id == tenant_id)
    if status_filter:
        if status_filter not in _ALLOWED_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown status: {status_filter}. Allowed: {sorted(_ALLOWED_STATUSES)}",
            )
        q = q.where(StockReservation.status == status_filter)
    q = q.order_by(StockReservation.created_at.desc())
    return list(db.execute(q).scalars().all())


@router.post("/{reservation_id}/release", status_code=status.HTTP_204_NO_CONTENT)
def release(
    reservation_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    res = db.get(StockReservation, reservation_id)
    if res is None or res.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found",
        )
    if res.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot release a reservation with status={res.status!r}; only 'active' reservations can be released",
        )
    release_reservation(db, res.id)
    db.commit()


@router.post("/sweep-expired", response_model=SweepResponse)
def sweep(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SweepResponse:
    """Trigger an immediate sweep of all expired reservations across the tenant."""
    _require_tenant(ctx)
    count = sweep_expired(db)
    db.commit()
    return SweepResponse(expired_count=count)
