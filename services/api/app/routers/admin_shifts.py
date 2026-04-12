"""Admin shifts endpoints — open, list, and close register sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, AdminContext, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import PaymentAllocation, Shop, ShiftClosing, Transaction

router = APIRouter(prefix="/v1/admin/shifts", tags=["Admin Shifts"])


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


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ShiftOut(BaseModel):
    id: UUID
    shop_id: UUID
    shop_name: str | None
    opened_at: str
    closed_at: str | None
    status: str
    expected_cash_cents: int
    reported_cash_cents: int
    discrepancy_cents: int
    notes: str | None
    transaction_count: int
    gross_cents: int


class ShiftListResponse(BaseModel):
    items: list[ShiftOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _shift_tx_stats(db: Session, shift: ShiftClosing) -> tuple[int, int]:
    """Return (transaction_count, gross_cents) for a shift by time window."""
    end = shift.closed_at or datetime.now(UTC)
    row = db.execute(
        select(
            func.count(Transaction.id).label("cnt"),
            func.coalesce(func.sum(Transaction.total_cents), 0).label("gross"),
        ).where(
            Transaction.shop_id == shift.shop_id,
            Transaction.created_at >= shift.opened_at,
            Transaction.created_at <= end,
            Transaction.status == "posted",
        )
    ).one()
    return int(row.cnt), int(row.gross)


def _expected_cash_cents(db: Session, shop_id, tenant_id, opened_at, closed_at) -> int:
    """Sum only cash-tender payment allocations within the shift window."""
    return int(db.execute(
        select(func.coalesce(func.sum(PaymentAllocation.amount_cents), 0))
        .join(Transaction, Transaction.id == PaymentAllocation.transaction_id)
        .where(
            Transaction.shop_id == shop_id,
            Transaction.tenant_id == tenant_id,
            Transaction.created_at >= opened_at,
            Transaction.created_at <= closed_at,
            Transaction.status == "posted",
            PaymentAllocation.tender_type == "cash",
        )
    ).scalar_one())


def _build_shift_out(db: Session, shift: ShiftClosing, shop_name: str | None) -> ShiftOut:
    tx_count, gross = _shift_tx_stats(db, shift)
    return ShiftOut(
        id=shift.id,
        shop_id=shift.shop_id,
        shop_name=shop_name,
        opened_at=shift.opened_at.isoformat(),
        closed_at=shift.closed_at.isoformat() if shift.closed_at else None,
        status=shift.status,
        expected_cash_cents=shift.expected_cash_cents,
        reported_cash_cents=shift.reported_cash_cents,
        discrepancy_cents=shift.discrepancy_cents,
        notes=shift.notes,
        transaction_count=tx_count,
        gross_cents=gross,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ShiftListResponse, dependencies=[require_permission("operations:read")])
def list_shifts(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    shop_id: UUID | None = Query(default=None),
    shift_status: str | None = Query(default=None, alias="status"),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> ShiftListResponse:
    tenant_id = _require_operator_tenant(ctx)

    stmt = (
        select(ShiftClosing)
        .where(ShiftClosing.tenant_id == tenant_id)
        .order_by(ShiftClosing.opened_at.desc())
        .limit(limit)
    )
    if shop_id is not None:
        stmt = stmt.where(ShiftClosing.shop_id == shop_id)
    if shift_status in ("open", "closed"):
        stmt = stmt.where(ShiftClosing.status == shift_status)
    if from_date:
        stmt = stmt.where(ShiftClosing.opened_at >= from_date)
    if to_date:
        stmt = stmt.where(ShiftClosing.opened_at <= to_date + "T23:59:59")

    shifts = db.execute(stmt).scalars().all()

    shop_ids = {s.shop_id for s in shifts}
    shops = {
        s.id: s.name
        for s in db.execute(select(Shop).where(Shop.id.in_(shop_ids))).scalars().all()
    } if shop_ids else {}

    return ShiftListResponse(
        items=[_build_shift_out(db, s, shops.get(s.shop_id)) for s in shifts]
    )


class OpenShiftBody(BaseModel):
    shop_id: UUID
    notes: str | None = None


@router.post("", response_model=ShiftOut, status_code=status.HTTP_201_CREATED, dependencies=[require_permission("operations:write")])
def open_shift(
    body: OpenShiftBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShiftOut:
    tenant_id = _require_operator_tenant(ctx)

    shop = db.get(Shop, body.shop_id)
    if shop is None or shop.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

    shift = ShiftClosing(
        tenant_id=tenant_id,
        shop_id=body.shop_id,
        opened_at=datetime.now(UTC),
        status="open",
        expected_cash_cents=0,
        reported_cash_cents=0,
        discrepancy_cents=0,
        notes=body.notes,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return _build_shift_out(db, shift, shop.name)


class CloseShiftBody(BaseModel):
    reported_cash_cents: int = Field(ge=0)
    notes: str | None = None


@router.patch("/{shift_id}/close", response_model=ShiftOut, dependencies=[require_permission("operations:write")])
def close_shift(
    shift_id: UUID,
    body: CloseShiftBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShiftOut:
    tenant_id = _require_operator_tenant(ctx)

    shift = db.get(ShiftClosing, shift_id)
    if shift is None or shift.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
    if shift.status != "open":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Shift is already closed",
        )

    now = datetime.now(UTC)

    # Compute expected from cash-only payment allocations in the shift window
    expected = _expected_cash_cents(db, shift.shop_id, tenant_id, shift.opened_at, now)

    shift.closed_at = now
    shift.status = "closed"
    shift.expected_cash_cents = expected
    shift.reported_cash_cents = body.reported_cash_cents
    shift.discrepancy_cents = body.reported_cash_cents - expected
    if body.notes:
        shift.notes = (shift.notes or "") + ("\n" if shift.notes else "") + body.notes
    if ctx.operator_id:
        shift.closed_by = ctx.operator_id

    db.commit()
    db.refresh(shift)

    shop = db.get(Shop, shift.shop_id)
    return _build_shift_out(db, shift, shop.name if shop else None)
