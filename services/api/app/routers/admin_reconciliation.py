"""Admin reconciliation endpoints — derived from shift_closings."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, AdminContext
from app.db.admin_deps_db import get_db_admin
from app.models import AdminUser, Shop, ShiftClosing

router = APIRouter(prefix="/v1/admin/reconciliation", tags=["Admin Reconciliation"])


def _require_operator_tenant(ctx: AdminContext) -> UUID:
    if ctx.is_legacy_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy admin token is not allowed for this endpoint",
        )
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator account has no tenant assigned",
        )
    return ctx.tenant_id


class ReconciliationRow(BaseModel):
    id: UUID
    period: str
    shop_id: UUID
    shop_name: str | None
    expected_cents: int
    actual_cents: int
    variance_cents: int
    rec_status: str
    opened_at: str
    closed_at: str | None
    resolution_note: str | None


class ReconciliationListResponse(BaseModel):
    items: list[ReconciliationRow]


def _rec_status(shift: ShiftClosing) -> tuple[str, str | None]:
    """Return (status, resolution_note) from a closed shift."""
    notes = shift.notes or ""
    if "[RESOLVED" in notes:
        # Extract the resolution note portion
        idx = notes.find("[RESOLVED")
        return "resolved", notes[idx:]
    if shift.discrepancy_cents == 0:
        return "matched", None
    return "variance", None


@router.get("", response_model=ReconciliationListResponse)
def list_reconciliation(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    shop_id: UUID | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
) -> ReconciliationListResponse:
    tenant_id = _require_operator_tenant(ctx)

    stmt = (
        select(ShiftClosing)
        .where(ShiftClosing.tenant_id == tenant_id, ShiftClosing.status == "closed")
        .order_by(ShiftClosing.closed_at.desc())
    )
    if shop_id is not None:
        stmt = stmt.where(ShiftClosing.shop_id == shop_id)
    if from_date:
        stmt = stmt.where(ShiftClosing.closed_at >= from_date)
    if to_date:
        stmt = stmt.where(ShiftClosing.closed_at <= to_date + "T23:59:59")

    shifts = db.execute(stmt).scalars().all()

    shop_ids = {s.shop_id for s in shifts}
    shops = {
        s.id: s.name
        for s in db.execute(select(Shop).where(Shop.id.in_(shop_ids))).scalars().all()
    } if shop_ids else {}

    items = []
    for shift in shifts:
        rec_st, resolution_note = _rec_status(shift)
        shop_name = shops.get(shift.shop_id)
        period = f"{shop_name or 'Unknown'} — {shift.closed_at.strftime('%b %d, %Y') if shift.closed_at else '?'}"
        items.append(ReconciliationRow(
            id=shift.id,
            period=period,
            shop_id=shift.shop_id,
            shop_name=shop_name,
            expected_cents=shift.expected_cash_cents,
            actual_cents=shift.reported_cash_cents,
            variance_cents=shift.discrepancy_cents,
            rec_status=rec_st,
            opened_at=shift.opened_at.isoformat(),
            closed_at=shift.closed_at.isoformat() if shift.closed_at else None,
            resolution_note=resolution_note,
        ))

    return ReconciliationListResponse(items=items)


class ResolveBody(BaseModel):
    resolution_notes: str = Field(min_length=1, max_length=1000)


@router.patch("/{shift_id}/resolve", response_model=ReconciliationRow)
def resolve_reconciliation(
    shift_id: UUID,
    body: ResolveBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ReconciliationRow:
    tenant_id = _require_operator_tenant(ctx)

    shift = db.get(ShiftClosing, shift_id)
    if shift is None or shift.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
    if shift.status != "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shift must be closed to resolve")
    if shift.discrepancy_cents == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No variance to resolve")

    # Fetch operator email for the resolution note
    operator_email = "operator"
    if ctx.operator_id:
        op = db.get(AdminUser, ctx.operator_id)
        if op:
            operator_email = op.email

    from datetime import UTC, datetime
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    resolution_line = f"\n[RESOLVED by {operator_email} on {timestamp}]: {body.resolution_notes}"
    shift.notes = (shift.notes or "") + resolution_line

    db.commit()
    db.refresh(shift)

    shop = db.get(Shop, shift.shop_id)
    shop_name = shop.name if shop else None
    rec_st, resolution_note = _rec_status(shift)
    period = f"{shop_name or 'Unknown'} — {shift.closed_at.strftime('%b %d, %Y') if shift.closed_at else '?'}"

    return ReconciliationRow(
        id=shift.id,
        period=period,
        shop_id=shift.shop_id,
        shop_name=shop_name,
        expected_cents=shift.expected_cash_cents,
        actual_cents=shift.reported_cash_cents,
        variance_cents=shift.discrepancy_cents,
        rec_status=rec_st,
        opened_at=shift.opened_at.isoformat(),
        closed_at=shift.closed_at.isoformat() if shift.closed_at else None,
        resolution_note=resolution_note,
    )
