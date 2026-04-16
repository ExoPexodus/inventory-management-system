"""Plans & add-ons CRUD for the platform portal."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import OperatorDep
from app.db.session import get_db
from app.models.tables import Addon, Plan
from app.services.audit_service import write_audit

router = APIRouter(prefix="/v1/platform", tags=["Platform Plans & Addons"])


# ---------------------------------------------------------------------------
# Plan schemas
# ---------------------------------------------------------------------------


class PlanCreate(BaseModel):
    codename: str
    display_name: str
    description: str | None = None
    base_price_cents: int
    currency_code: str = "INR"
    yearly_discount_pct: int = 0
    max_shops: int = 1
    max_employees: int = 5
    storage_limit_mb: int = 500


class PlanPatch(BaseModel):
    display_name: str | None = None
    description: str | None = None
    base_price_cents: int | None = None
    currency_code: str | None = None
    yearly_discount_pct: int | None = None
    max_shops: int | None = None
    max_employees: int | None = None
    storage_limit_mb: int | None = None
    is_active: bool | None = None


class PlanOut(BaseModel):
    id: UUID
    codename: str
    display_name: str
    description: str | None
    base_price_cents: int
    currency_code: str
    yearly_discount_pct: int
    max_shops: int
    max_employees: int
    storage_limit_mb: int
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Addon schemas
# ---------------------------------------------------------------------------


class AddonCreate(BaseModel):
    codename: str
    display_name: str
    description: str | None = None
    price_cents: int
    currency_code: str = "INR"


class AddonPatch(BaseModel):
    display_name: str | None = None
    description: str | None = None
    price_cents: int | None = None
    currency_code: str | None = None
    is_active: bool | None = None


class AddonOut(BaseModel):
    id: UUID
    codename: str
    display_name: str
    description: str | None
    price_cents: int
    currency_code: str
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Plan endpoints
# ---------------------------------------------------------------------------


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> list[PlanOut]:
    rows = db.execute(select(Plan).order_by(Plan.base_price_cents)).scalars().all()
    return [_plan_out(p) for p in rows]


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    body: PlanCreate,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> PlanOut:
    plan = Plan(**body.model_dump())
    db.add(plan)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plan codename already exists")

    write_audit(db, operator_id=ctx.operator_id, action="create_plan", resource_type="plan", resource_id=str(plan.id))
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def patch_plan(
    plan_id: UUID,
    body: PlanPatch,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> PlanOut:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    patch = body.model_dump(exclude_unset=True)
    for key, val in patch.items():
        setattr(plan, key, val)

    write_audit(db, operator_id=ctx.operator_id, action="update_plan", resource_type="plan", resource_id=str(plan_id), details=patch)
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)


# ---------------------------------------------------------------------------
# Addon endpoints
# ---------------------------------------------------------------------------


@router.get("/addons", response_model=list[AddonOut])
def list_addons(
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> list[AddonOut]:
    rows = db.execute(select(Addon).order_by(Addon.price_cents)).scalars().all()
    return [_addon_out(a) for a in rows]


@router.post("/addons", response_model=AddonOut, status_code=status.HTTP_201_CREATED)
def create_addon(
    body: AddonCreate,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> AddonOut:
    addon = Addon(**body.model_dump())
    db.add(addon)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Addon codename already exists")

    write_audit(db, operator_id=ctx.operator_id, action="create_addon", resource_type="addon", resource_id=str(addon.id))
    db.commit()
    db.refresh(addon)
    return _addon_out(addon)


@router.patch("/addons/{addon_id}", response_model=AddonOut)
def patch_addon(
    addon_id: UUID,
    body: AddonPatch,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> AddonOut:
    addon = db.get(Addon, addon_id)
    if addon is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found")

    patch = body.model_dump(exclude_unset=True)
    for key, val in patch.items():
        setattr(addon, key, val)

    write_audit(db, operator_id=ctx.operator_id, action="update_addon", resource_type="addon", resource_id=str(addon_id), details=patch)
    db.commit()
    db.refresh(addon)
    return _addon_out(addon)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _plan_out(p: Plan) -> PlanOut:
    return PlanOut(
        id=p.id,
        codename=p.codename,
        display_name=p.display_name,
        description=p.description,
        base_price_cents=p.base_price_cents,
        currency_code=p.currency_code,
        yearly_discount_pct=p.yearly_discount_pct,
        max_shops=p.max_shops,
        max_employees=p.max_employees,
        storage_limit_mb=p.storage_limit_mb,
        is_active=p.is_active,
        created_at=p.created_at,
    )


def _addon_out(a: Addon) -> AddonOut:
    return AddonOut(
        id=a.id,
        codename=a.codename,
        display_name=a.display_name,
        description=a.description,
        price_cents=a.price_cents,
        currency_code=a.currency_code,
        is_active=a.is_active,
        created_at=a.created_at,
    )
