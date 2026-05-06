"""Admin endpoints for managing FX rates (manual upload).

Auth: requires `currency:manage` permission.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.billing.fx import set_rate
from app.db.admin_deps_db import get_db_admin
from app.models import FxRate

router = APIRouter(
    prefix="/v1/admin/fx-rates",
    tags=["Admin FX Rates"],
    dependencies=[require_permission("currency:manage")],
)


class FxRateIn(BaseModel):
    from_currency: str = Field(min_length=3, max_length=3)
    to_currency: str = Field(min_length=3, max_length=3)
    rate: str  # parsed as Decimal in the route

    @field_validator("rate")
    @classmethod
    def _rate_is_parseable(cls, v: str) -> str:
        try:
            Decimal(v)
        except (InvalidOperation, ValueError):
            raise ValueError(f"rate must be a numeric string, got {v!r}")
        return v


class FxRateOut(BaseModel):
    id: UUID
    tenant_id: UUID
    from_currency: str
    to_currency: str
    rate: str
    source: str
    effective_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("rate", mode="before")
    @classmethod
    def _stringify_rate(cls, v) -> str:
        return str(v)


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


@router.get("", response_model=list[FxRateOut])
def list_rates(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[FxRate]:
    tenant_id = _require_tenant(ctx)
    rows = db.execute(
        select(FxRate).where(FxRate.tenant_id == tenant_id).order_by(
            FxRate.from_currency, FxRate.to_currency,
        )
    ).scalars().all()
    return list(rows)


@router.post("", response_model=FxRateOut, status_code=status.HTTP_201_CREATED)
def create_or_update_rate(
    body: FxRateIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> FxRate:
    tenant_id = _require_tenant(ctx)
    rate = Decimal(body.rate)
    if rate <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rate must be positive",
        )
    row = set_rate(db, tenant_id, body.from_currency, body.to_currency, rate)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rate(
    rate_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    row = db.get(FxRate, rate_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    db.delete(row)
    db.commit()
