"""Device-auth shift endpoints — cashier-owned shift open/close."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import DeviceAuth, get_device_auth
from app.db.session import get_db
from app.models import PaymentAllocation, ShiftClosing, Transaction

router = APIRouter(prefix="/v1/shifts", tags=["Device Shifts"])

DeviceAuthDep = Annotated[DeviceAuth, Depends(get_device_auth)]


class ShiftOut(BaseModel):
    id: UUID
    shop_id: UUID
    opened_at: str
    closed_at: str | None
    status: str
    expected_cash_cents: int
    reported_cash_cents: int
    discrepancy_cents: int
    notes: str | None


class OpenShiftBody(BaseModel):
    notes: str | None = None


class CloseShiftBody(BaseModel):
    reported_cash_cents: int = Field(ge=0)
    notes: str | None = None


def _cash_expected(db: Session, shop_id: UUID, tenant_id: UUID, opened_at: datetime, closed_at: datetime) -> int:
    """Sum cash-tender allocations within the shift window."""
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


def _to_out(shift: ShiftClosing) -> ShiftOut:
    return ShiftOut(
        id=shift.id,
        shop_id=shift.shop_id,
        opened_at=shift.opened_at.isoformat(),
        closed_at=shift.closed_at.isoformat() if shift.closed_at else None,
        status=shift.status,
        expected_cash_cents=shift.expected_cash_cents,
        reported_cash_cents=shift.reported_cash_cents,
        discrepancy_cents=shift.discrepancy_cents,
        notes=shift.notes,
    )


@router.get("/active", response_model=ShiftOut)
def get_active_shift(
    ctx: DeviceAuthDep,
    db: Annotated[Session, Depends(get_db)],
) -> ShiftOut:
    """Return the currently open shift for this device's shop, or 404."""
    if not ctx.shop_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device has no shop assigned")
    shop_id = ctx.shop_ids[0]
    shift = db.execute(
        select(ShiftClosing)
        .where(ShiftClosing.shop_id == shop_id, ShiftClosing.status == "open")
        .order_by(ShiftClosing.opened_at.desc())
    ).scalars().first()
    if not shift:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No open shift for this shop")
    return _to_out(shift)


@router.post("", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
def open_shift(
    body: OpenShiftBody,
    ctx: DeviceAuthDep,
    db: Annotated[Session, Depends(get_db)],
) -> ShiftOut:
    """Open a new shift. Enforces one open shift per shop."""
    if not ctx.shop_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device has no shop assigned")
    shop_id = ctx.shop_ids[0]

    existing = db.execute(
        select(ShiftClosing).where(
            ShiftClosing.shop_id == shop_id,
            ShiftClosing.status == "open",
        )
    ).scalars().first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A shift is already open for this shop",
        )

    shift = ShiftClosing(
        tenant_id=ctx.tenant_id,
        shop_id=shop_id,
        device_id=ctx.device_id,
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
    return _to_out(shift)


@router.patch("/{shift_id}/close", response_model=ShiftOut)
def close_shift(
    shift_id: UUID,
    body: CloseShiftBody,
    ctx: DeviceAuthDep,
    db: Annotated[Session, Depends(get_db)],
) -> ShiftOut:
    """Close a shift with the cashier's physical cash count."""
    shift = db.get(ShiftClosing, shift_id)
    if not shift or shift.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
    if shift.status != "open":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shift is already closed")

    now = datetime.now(UTC)
    expected = _cash_expected(db, shift.shop_id, ctx.tenant_id, shift.opened_at, now)

    shift.closed_at = now
    shift.status = "closed"
    shift.expected_cash_cents = expected
    shift.reported_cash_cents = body.reported_cash_cents
    shift.discrepancy_cents = body.reported_cash_cents - expected
    if body.notes:
        shift.notes = (shift.notes or "") + ("\n" if shift.notes else "") + body.notes
    # reviewed_by left null — pending manager review

    db.commit()
    db.refresh(shift)
    return _to_out(shift)
