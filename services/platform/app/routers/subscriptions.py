"""Subscription management endpoints for the platform portal."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import OperatorDep
from app.db.session import get_db
from app.models.tables import Addon, Plan, Subscription, SubscriptionAddon
from app.services.audit_service import write_audit
from app.services.subscription_service import (
    activate_subscription,
    add_addon,
    cancel_subscription,
    create_subscription,
    remove_addon,
    suspend_subscription,
)

router = APIRouter(prefix="/v1/platform", tags=["Platform Subscriptions"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SubscriptionCreate(BaseModel):
    plan_id: UUID
    billing_cycle: str = "monthly"
    is_trial: bool = False
    trial_days: int = 14
    grace_period_days: int = 7


class SubscriptionPatch(BaseModel):
    billing_cycle: str | None = None
    grace_period_days: int | None = None


class AddonAction(BaseModel):
    addon_id: UUID


class SubscriptionAddonOut(BaseModel):
    addon_id: UUID
    codename: str
    display_name: str
    added_at: datetime


class SubscriptionOut(BaseModel):
    id: UUID
    tenant_id: UUID
    plan_id: UUID
    plan_codename: str
    plan_display_name: str
    status: str
    billing_cycle: str
    trial_ends_at: datetime | None
    current_period_start: datetime
    current_period_end: datetime
    grace_period_days: int
    cancelled_at: datetime | None
    addons: list[SubscriptionAddonOut]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# List all subscriptions
# ---------------------------------------------------------------------------


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def list_subscriptions(
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
    sub_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SubscriptionOut]:
    stmt = select(Subscription).order_by(Subscription.created_at.desc())
    if sub_status:
        stmt = stmt.where(Subscription.status == sub_status)
    stmt = stmt.limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [_to_out(db, s) for s in rows]


# ---------------------------------------------------------------------------
# Per-tenant subscription
# ---------------------------------------------------------------------------


@router.get("/tenants/{tenant_id}/subscription", response_model=SubscriptionOut)
def get_tenant_subscription(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    sub = _get_active_sub(db, tenant_id)
    return _to_out(db, sub)


@router.post("/tenants/{tenant_id}/subscription", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
def create_tenant_subscription(
    tenant_id: UUID,
    body: SubscriptionCreate,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    try:
        sub = create_subscription(
            db,
            tenant_id=tenant_id,
            plan_id=body.plan_id,
            billing_cycle=body.billing_cycle,
            is_trial=body.is_trial,
            trial_days=body.trial_days,
            grace_period_days=body.grace_period_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    write_audit(db, operator_id=ctx.operator_id, action="create_subscription", resource_type="subscription", resource_id=str(sub.id))
    db.commit()
    db.refresh(sub)
    return _to_out(db, sub)


@router.patch("/tenants/{tenant_id}/subscription", response_model=SubscriptionOut)
def patch_tenant_subscription(
    tenant_id: UUID,
    body: SubscriptionPatch,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    sub = _get_active_sub(db, tenant_id)
    patch = body.model_dump(exclude_unset=True)
    for key, val in patch.items():
        setattr(sub, key, val)

    write_audit(db, operator_id=ctx.operator_id, action="update_subscription", resource_type="subscription", resource_id=str(sub.id), details=patch)
    db.commit()
    db.refresh(sub)
    return _to_out(db, sub)


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


@router.post("/tenants/{tenant_id}/subscription/activate", response_model=SubscriptionOut)
def activate_sub(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    sub = _get_active_sub(db, tenant_id)
    try:
        activate_subscription(db, sub)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    write_audit(db, operator_id=ctx.operator_id, action="activate_subscription", resource_type="subscription", resource_id=str(sub.id))
    db.commit()
    db.refresh(sub)
    return _to_out(db, sub)


@router.post("/tenants/{tenant_id}/subscription/suspend", response_model=SubscriptionOut)
def suspend_sub(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    sub = _get_active_sub(db, tenant_id)
    try:
        suspend_subscription(db, sub)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    write_audit(db, operator_id=ctx.operator_id, action="suspend_subscription", resource_type="subscription", resource_id=str(sub.id))
    db.commit()
    db.refresh(sub)
    return _to_out(db, sub)


@router.post("/tenants/{tenant_id}/subscription/reactivate", response_model=SubscriptionOut)
def reactivate_sub(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    sub = _get_active_sub(db, tenant_id)
    try:
        activate_subscription(db, sub)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    write_audit(db, operator_id=ctx.operator_id, action="reactivate_subscription", resource_type="subscription", resource_id=str(sub.id))
    db.commit()
    db.refresh(sub)
    return _to_out(db, sub)


@router.post("/tenants/{tenant_id}/subscription/cancel", response_model=SubscriptionOut)
def cancel_sub(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    sub = _get_active_sub(db, tenant_id)
    try:
        cancel_subscription(db, sub)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    write_audit(db, operator_id=ctx.operator_id, action="cancel_subscription", resource_type="subscription", resource_id=str(sub.id))
    db.commit()
    db.refresh(sub)
    return _to_out(db, sub)


# ---------------------------------------------------------------------------
# Add-on management
# ---------------------------------------------------------------------------


@router.post("/tenants/{tenant_id}/subscription/addons", response_model=SubscriptionOut)
def add_subscription_addon(
    tenant_id: UUID,
    body: AddonAction,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    sub = _get_active_sub(db, tenant_id)
    try:
        add_addon(db, sub.id, body.addon_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    write_audit(db, operator_id=ctx.operator_id, action="add_addon", resource_type="subscription", resource_id=str(sub.id), details={"addon_id": str(body.addon_id)})
    db.commit()
    db.refresh(sub)
    return _to_out(db, sub)


@router.delete("/tenants/{tenant_id}/subscription/addons/{addon_id}", response_model=SubscriptionOut)
def remove_subscription_addon(
    tenant_id: UUID,
    addon_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionOut:
    sub = _get_active_sub(db, tenant_id)
    try:
        remove_addon(db, sub.id, addon_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    write_audit(db, operator_id=ctx.operator_id, action="remove_addon", resource_type="subscription", resource_id=str(sub.id), details={"addon_id": str(addon_id)})
    db.commit()
    db.refresh(sub)
    return _to_out(db, sub)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_active_sub(db: Session, tenant_id: UUID) -> Subscription:
    sub = db.execute(
        select(Subscription)
        .where(Subscription.tenant_id == tenant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No subscription found for this tenant")
    return sub


def _to_out(db: Session, sub: Subscription) -> SubscriptionOut:
    plan = db.get(Plan, sub.plan_id)

    addon_rows = db.execute(
        select(SubscriptionAddon, Addon)
        .join(Addon, Addon.id == SubscriptionAddon.addon_id)
        .where(
            SubscriptionAddon.subscription_id == sub.id,
            SubscriptionAddon.removed_at.is_(None),
        )
    ).all()

    addons_out = [
        SubscriptionAddonOut(
            addon_id=a.id,
            codename=a.codename,
            display_name=a.display_name,
            added_at=sa.added_at,
        )
        for sa, a in addon_rows
    ]

    return SubscriptionOut(
        id=sub.id,
        tenant_id=sub.tenant_id,
        plan_id=sub.plan_id,
        plan_codename=plan.codename if plan else "unknown",
        plan_display_name=plan.display_name if plan else "Unknown",
        status=sub.status,
        billing_cycle=sub.billing_cycle,
        trial_ends_at=sub.trial_ends_at,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        grace_period_days=sub.grace_period_days,
        cancelled_at=sub.cancelled_at,
        addons=addons_out,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )
