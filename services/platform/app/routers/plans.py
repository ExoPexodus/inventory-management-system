"""Plans & add-ons CRUD for the platform portal."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import OperatorDep
from app.config import settings
from app.db.session import get_db
from app.models.tables import Addon, Plan, PlanFeature, PlatformTenant, Subscription
from app.services.audit_service import write_audit
from app.services.feature_catalog import get_feature_catalog

logger = logging.getLogger(__name__)

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
# Plan features endpoints
# ---------------------------------------------------------------------------


@router.get("/plans/{plan_id}/features", response_model=dict[str, Any])
def get_plan_features(
    plan_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Returns {feature_key: value} for the plan."""
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    rows = db.execute(
        select(PlanFeature).where(PlanFeature.plan_id == plan_id)
    ).scalars().all()
    return {r.feature_key: r.value for r in rows}


@router.put("/plans/{plan_id}/features", response_model=dict[str, Any])
def put_plan_features(
    plan_id: UUID,
    body: dict[str, Any],
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
    apply_to_existing: bool = Query(default=False),
) -> dict[str, Any]:
    """Replace the plan's feature set. Validates keys against IMS catalog.

    If apply_to_existing=True, triggers immediate license sync for each
    tenant currently on this plan.
    """
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    # Validate keys against IMS catalog (best-effort — accept if catalog unavailable)
    catalog = get_feature_catalog()
    if catalog:
        unknown = [k for k in body if k not in catalog]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown feature key(s): {unknown}. Valid keys: {sorted(catalog.keys())}",
            )

    # Delete all existing feature rows for this plan then re-insert
    existing = db.execute(
        select(PlanFeature).where(PlanFeature.plan_id == plan_id)
    ).scalars().all()
    for row in existing:
        db.delete(row)
    db.flush()

    for feature_key, value in body.items():
        db.add(PlanFeature(plan_id=plan_id, feature_key=feature_key, value=value))

    write_audit(
        db, operator_id=ctx.operator_id, action="update_plan_features",
        resource_type="plan", resource_id=str(plan_id), details={"keys": list(body.keys())},
    )
    db.commit()

    if apply_to_existing:
        _cascade_sync_to_plan_tenants(db, plan_id)

    return body


# ---------------------------------------------------------------------------
# Plan delete endpoint
# ---------------------------------------------------------------------------


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Delete a plan. 409 if is_active=True or if any active subscriptions exist."""
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    if plan.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Plan must be archived (is_active=false) before deletion",
        )

    active_sub = db.execute(
        select(Subscription).where(
            Subscription.plan_id == plan_id,
            Subscription.cancelled_at.is_(None),
        )
    ).scalar_one_or_none()
    if active_sub is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Plan has active subscriptions — cancel or move all tenants first",
        )

    write_audit(db, operator_id=ctx.operator_id, action="delete_plan", resource_type="plan", resource_id=str(plan_id))
    db.delete(plan)
    db.commit()


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


def _cascade_sync_to_plan_tenants(db: Session, plan_id: UUID) -> None:
    """For every active subscription on this plan, trigger an IMS license sync.

    Uses per-tenant api_base_url so it works in multi-instance deployments.
    Errors per tenant are logged but do not abort the loop.
    """
    subs = db.execute(
        select(Subscription, PlatformTenant)
        .join(PlatformTenant, PlatformTenant.id == Subscription.tenant_id)
        .where(
            Subscription.plan_id == plan_id,
            Subscription.cancelled_at.is_(None),
        )
    ).all()

    secret = settings.platform_api_secret
    for sub, tenant in subs:
        try:
            ts = str(int(time.time()))
            msg = f"{ts}|{tenant.id}"
            sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
            url = f"{tenant.api_base_url}/v1/internal/license-sync-trigger"
            resp = httpx.post(
                url,
                json={"tenant_id": str(tenant.id)},
                headers={"X-Platform-Auth": sig, "X-Platform-Timestamp": ts},
                timeout=10.0,
            )
            if resp.status_code not in (200, 202):
                logger.warning(
                    "License sync trigger failed for tenant %s: HTTP %s",
                    tenant.id, resp.status_code,
                )
        except Exception:
            logger.warning("License sync trigger error for tenant %s", tenant.id, exc_info=True)


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
