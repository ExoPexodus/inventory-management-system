"""Admin endpoints for discounts + the public discount-apply endpoint."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Category, Discount, DiscountTier, DiscountUse
from app.services.discount_service import (
    CartLine,
    DiscountNotEligibleError, DiscountNotFoundError, apply_discount,
)

router = APIRouter(tags=["Admin Discounts"])

_VALID_TYPES = {"percentage", "fixed_amount", "free_shipping"}
_VALID_STATUSES = {"active", "paused", "scheduled"}
_VALID_SCOPES = {"none", "per_line", "cart_total"}


# --------------------------------------------------------------------------
# Input / output models
# --------------------------------------------------------------------------

class TierInput(BaseModel):
    threshold_quantity: int = Field(ge=1)
    value_bps: int | None = Field(default=None, ge=1, le=10000)
    value_cents: int | None = Field(default=None, ge=1)
    sort_order: int = 0


class TierOut(BaseModel):
    id: UUID
    threshold_quantity: int
    value_bps: int | None
    value_cents: int | None
    sort_order: int

    model_config = {"from_attributes": True}


class CartLineInput(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)
    unit_price_cents: int = Field(ge=0)


class DiscountIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=128)
    discount_type: str
    value_bps: int | None = Field(default=None, ge=1, le=10000)
    value_cents: int | None = Field(default=None, ge=1)
    channel_id: UUID | None = None
    status: str = "active"
    stackable: bool = False
    priority: int = 0
    min_subtotal_cents: int | None = Field(default=None, ge=0)
    max_uses_total: int | None = Field(default=None, ge=1)
    max_uses_per_customer: int | None = Field(default=None, ge=1)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    # Condition fields
    condition_quantity_scope: str = "none"
    condition_min_quantity: int | None = Field(default=None, ge=1)
    condition_category_id: UUID | None = None
    condition_tag: str | None = Field(default=None, max_length=64)
    tiers: list[TierInput] | None = None


class DiscountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    stackable: bool | None = None
    priority: int | None = None
    min_subtotal_cents: int | None = None
    max_uses_total: int | None = None
    max_uses_per_customer: int | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    # Condition fields
    condition_quantity_scope: str | None = None
    condition_min_quantity: int | None = None
    condition_category_id: UUID | None = None
    condition_tag: str | None = None
    tiers: list[TierInput] | None = None


class DiscountOut(BaseModel):
    id: UUID
    tenant_id: UUID
    channel_id: UUID | None
    name: str
    code: str | None
    discount_type: str
    value_bps: int | None
    value_cents: int | None
    status: str
    stackable: bool
    priority: int
    min_subtotal_cents: int | None
    max_uses_total: int | None
    max_uses_per_customer: int | None
    starts_at: datetime | None
    expires_at: datetime | None
    times_used: int
    created_at: datetime
    updated_at: datetime
    # Condition fields
    condition_quantity_scope: str
    condition_min_quantity: int | None
    condition_category_id: UUID | None
    condition_tag: str | None
    tiers: list[TierOut]

    model_config = {"from_attributes": True}


class DiscountApplyIn(BaseModel):
    channel_id: UUID
    code: str | None = None
    cart_subtotal_cents: int = Field(ge=0)
    customer_id: UUID | None = None
    cart_lines: list[CartLineInput] | None = None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_or_404(db: Session, discount_id: UUID, tenant_id: UUID) -> Discount:
    d = db.get(Discount, discount_id)
    if d is None or d.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Discount not found")
    return d


def _times_used(db: Session, discount_id: UUID) -> int:
    return db.execute(
        select(func.count(DiscountUse.id)).where(DiscountUse.discount_id == discount_id)
    ).scalar_one()


def _load_tiers_map(db: Session, discount_ids: list[UUID]) -> dict[UUID, list[DiscountTier]]:
    """Load all tiers for the given discount IDs in one query. Returns dict keyed by discount_id."""
    if not discount_ids:
        return {}
    rows = db.execute(
        select(DiscountTier)
        .where(DiscountTier.discount_id.in_(discount_ids))
        .order_by(DiscountTier.discount_id, DiscountTier.sort_order, DiscountTier.threshold_quantity)
    ).scalars().all()
    result: dict[UUID, list[DiscountTier]] = {did: [] for did in discount_ids}
    for tier in rows:
        result[tier.discount_id].append(tier)
    return result


def _to_out(d: Discount, tiers: list[DiscountTier], times_used: int) -> DiscountOut:
    return DiscountOut(
        id=d.id, tenant_id=d.tenant_id, channel_id=d.channel_id,
        name=d.name, code=d.code, discount_type=d.discount_type,
        value_bps=d.value_bps, value_cents=d.value_cents,
        status=d.status, stackable=d.stackable, priority=d.priority,
        min_subtotal_cents=d.min_subtotal_cents,
        max_uses_total=d.max_uses_total, max_uses_per_customer=d.max_uses_per_customer,
        starts_at=d.starts_at, expires_at=d.expires_at,
        times_used=times_used,
        created_at=d.created_at, updated_at=d.updated_at,
        condition_quantity_scope=d.condition_quantity_scope,
        condition_min_quantity=d.condition_min_quantity,
        condition_category_id=d.condition_category_id,
        condition_tag=d.condition_tag,
        tiers=[TierOut(
            id=t.id, threshold_quantity=t.threshold_quantity,
            value_bps=t.value_bps, value_cents=t.value_cents, sort_order=t.sort_order,
        ) for t in tiers],
    )


def _validate_discount_type_and_value(
    discount_type: str,
    value_bps: int | None,
    value_cents: int | None,
    tiers: list[TierInput] | None,
) -> None:
    """Validate cross-field constraints, raising HTTP 400 on failure."""
    if discount_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"discount_type must be one of {sorted(_VALID_TYPES)}",
        )
    has_tiers = bool(tiers)
    if discount_type == "percentage":
        if not has_tiers and not value_bps:
            raise HTTPException(
                status_code=400,
                detail="value_bps is required for percentage discounts without tiers",
            )
    if discount_type == "fixed_amount":
        if not has_tiers and not value_cents:
            raise HTTPException(
                status_code=400,
                detail="value_cents is required for fixed_amount discounts without tiers",
            )


def _validate_condition_fields(
    scope: str,
    condition_min_quantity: int | None,
    tiers: list[TierInput] | None,
    discount_type: str,
    category_id: UUID | None,
    db: Session,
    tenant_id: UUID,
) -> None:
    """Validate condition/tier coherence; raises HTTP 422 on failure."""
    if scope not in _VALID_SCOPES:
        raise HTTPException(
            status_code=422,
            detail=f"condition_quantity_scope must be one of {sorted(_VALID_SCOPES)}",
        )
    if scope == "none" and condition_min_quantity is not None:
        raise HTTPException(
            status_code=422,
            detail="condition_min_quantity requires condition_quantity_scope to be 'per_line' or 'cart_total'",
        )
    has_tiers = bool(tiers)
    if scope == "none" and has_tiers:
        raise HTTPException(
            status_code=422,
            detail="Tiers require condition_quantity_scope to be 'per_line' or 'cart_total'",
        )

    if has_tiers and discount_type != "free_shipping":
        # All tiers must use the same value field matching discount_type
        for tier in tiers:
            if discount_type == "percentage" and not tier.value_bps:
                raise HTTPException(
                    status_code=422,
                    detail="All tiers for a percentage discount must have value_bps set",
                )
            if discount_type == "fixed_amount" and not tier.value_cents:
                raise HTTPException(
                    status_code=422,
                    detail="All tiers for a fixed_amount discount must have value_cents set",
                )

    # Validate category belongs to tenant
    if category_id is not None:
        cat = db.get(Category, category_id)
        if cat is None or cat.tenant_id != tenant_id:
            raise HTTPException(
                status_code=422,
                detail="condition_category_id not found for this tenant",
            )


def _upsert_tiers(
    db: Session,
    discount_id: UUID,
    tenant_id: UUID,
    tiers: list[TierInput],
) -> None:
    """Delete existing tiers for the discount and insert new ones."""
    db.execute(
        delete(DiscountTier).where(DiscountTier.discount_id == discount_id)
    )
    for t in tiers:
        db.add(DiscountTier(
            tenant_id=tenant_id,
            discount_id=discount_id,
            threshold_quantity=t.threshold_quantity,
            value_bps=t.value_bps,
            value_cents=t.value_cents,
            sort_order=t.sort_order,
        ))


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/v1/admin/discounts", response_model=list[DiscountOut],
            dependencies=[require_permission("discounts:manage")])
def list_discounts(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[DiscountOut]:
    tenant_id = _require_tenant(ctx)
    rows = db.execute(
        select(Discount).where(Discount.tenant_id == tenant_id)
        .order_by(Discount.priority.desc(), Discount.name)
    ).scalars().all()

    discount_ids = [r.id for r in rows]
    tiers_map = _load_tiers_map(db, discount_ids)

    # Batch load times_used to avoid N+1
    use_counts: dict[UUID, int] = {}
    if discount_ids:
        count_rows = db.execute(
            select(DiscountUse.discount_id, func.count(DiscountUse.id))
            .where(DiscountUse.discount_id.in_(discount_ids))
            .group_by(DiscountUse.discount_id)
        ).all()
        use_counts = {row[0]: row[1] for row in count_rows}

    return [_to_out(r, tiers_map.get(r.id, []), use_counts.get(r.id, 0)) for r in rows]


@router.post("/v1/admin/discounts", response_model=DiscountOut,
             status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("discounts:manage")])
def create_discount(
    body: DiscountIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> DiscountOut:
    tenant_id = _require_tenant(ctx)
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_VALID_STATUSES)}")
    _validate_discount_type_and_value(body.discount_type, body.value_bps, body.value_cents, body.tiers)

    scope = body.condition_quantity_scope
    _validate_condition_fields(
        scope=scope,
        condition_min_quantity=body.condition_min_quantity,
        tiers=body.tiers,
        discount_type=body.discount_type,
        category_id=body.condition_category_id,
        db=db,
        tenant_id=tenant_id,
    )

    condition_tag = body.condition_tag.lower().strip() if body.condition_tag else None

    disc = Discount(
        tenant_id=tenant_id,
        channel_id=body.channel_id,
        name=body.name,
        code=body.code.upper() if body.code else None,
        discount_type=body.discount_type,
        value_bps=body.value_bps,
        value_cents=body.value_cents,
        status=body.status,
        stackable=body.stackable,
        priority=body.priority,
        min_subtotal_cents=body.min_subtotal_cents,
        max_uses_total=body.max_uses_total,
        max_uses_per_customer=body.max_uses_per_customer,
        starts_at=body.starts_at,
        expires_at=body.expires_at,
        condition_quantity_scope=scope,
        condition_min_quantity=body.condition_min_quantity,
        condition_category_id=body.condition_category_id,
        condition_tag=condition_tag,
    )
    db.add(disc)
    try:
        db.flush()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409,
                            detail=f"A discount with code {body.code!r} already exists for this tenant")

    if body.tiers:
        _upsert_tiers(db, disc.id, tenant_id, body.tiers)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409,
                            detail=f"A discount with code {body.code!r} already exists for this tenant")

    db.refresh(disc)
    tiers = list(db.execute(
        select(DiscountTier).where(DiscountTier.discount_id == disc.id)
        .order_by(DiscountTier.sort_order, DiscountTier.threshold_quantity)
    ).scalars().all())
    return _to_out(disc, tiers, 0)


@router.get("/v1/admin/discounts/{discount_id}", response_model=DiscountOut,
            dependencies=[require_permission("discounts:manage")])
def get_discount(
    discount_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> DiscountOut:
    tenant_id = _require_tenant(ctx)
    disc = _get_or_404(db, discount_id, tenant_id)
    tiers = list(db.execute(
        select(DiscountTier).where(DiscountTier.discount_id == disc.id)
        .order_by(DiscountTier.sort_order, DiscountTier.threshold_quantity)
    ).scalars().all())
    times_used = _times_used(db, disc.id)
    return _to_out(disc, tiers, times_used)


@router.patch("/v1/admin/discounts/{discount_id}", response_model=DiscountOut,
              dependencies=[require_permission("discounts:manage")])
def update_discount(
    discount_id: UUID,
    body: DiscountPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> DiscountOut:
    tenant_id = _require_tenant(ctx)
    disc = _get_or_404(db, discount_id, tenant_id)
    updates = body.model_dump(exclude_unset=True)

    if "status" in updates and updates["status"] not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_VALID_STATUSES)}")

    # Lowercase tag if provided
    if "condition_tag" in updates and updates["condition_tag"]:
        updates["condition_tag"] = updates["condition_tag"].lower().strip()

    # Determine effective values after patch for validation
    # tiers_in_patch is a list of dicts (from model_dump) or None if not sent
    tiers_raw = updates.pop("tiers", None)  # Handle separately

    effective_scope = updates.get("condition_quantity_scope", disc.condition_quantity_scope)
    effective_min_qty = updates.get("condition_min_quantity", disc.condition_min_quantity)
    effective_category_id = updates.get("condition_category_id", disc.condition_category_id)

    # Convert raw dicts to TierInput objects if tiers were sent
    tiers_in_patch: list[TierInput] | None = (
        [TierInput(**t) for t in tiers_raw] if tiers_raw is not None else None
    )

    # Load current tiers to determine if tiers exist after this patch
    current_tiers = list(db.execute(
        select(DiscountTier).where(DiscountTier.discount_id == disc.id)
    ).scalars().all())
    # tiers_in_patch=None means don't touch; empty list means clear; non-empty means replace
    if tiers_in_patch is None:
        effective_tiers_exist = bool(current_tiers)
    else:
        effective_tiers_exist = bool(tiers_in_patch)

    effective_discount_type = disc.discount_type

    # Validate condition coherence with effective state
    _validate_condition_fields(
        scope=effective_scope,
        condition_min_quantity=effective_min_qty,
        tiers=tiers_in_patch if tiers_in_patch is not None else (
            [TierInput(threshold_quantity=t.threshold_quantity, value_bps=t.value_bps,
                       value_cents=t.value_cents, sort_order=t.sort_order)
             for t in current_tiers] if effective_tiers_exist else []
        ),
        discount_type=effective_discount_type,
        category_id=effective_category_id,
        db=db,
        tenant_id=tenant_id,
    )

    for field, value in updates.items():
        setattr(disc, field, value)

    if tiers_in_patch is not None:
        _upsert_tiers(db, disc.id, tenant_id, tiers_in_patch)

    db.commit()
    db.refresh(disc)
    tiers = list(db.execute(
        select(DiscountTier).where(DiscountTier.discount_id == disc.id)
        .order_by(DiscountTier.sort_order, DiscountTier.threshold_quantity)
    ).scalars().all())
    times_used = _times_used(db, disc.id)
    return _to_out(disc, tiers, times_used)


@router.delete("/v1/admin/discounts/{discount_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_permission("discounts:manage")])
def delete_discount(
    discount_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    disc = _get_or_404(db, discount_id, tenant_id)
    db.delete(disc)
    db.commit()


@router.post("/v1/discounts/apply")
def apply(
    body: DiscountApplyIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict[str, Any]:
    """Public discount calculator. Returns 404 if code not found, 422 if ineligible."""
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")

    lines = None
    if body.cart_lines is not None:
        lines = [
            CartLine(
                product_id=cl.product_id,
                quantity=cl.quantity,
                unit_price_cents=cl.unit_price_cents,
            )
            for cl in body.cart_lines
        ]

    try:
        return apply_discount(
            db, tenant_id=ctx.tenant_id, channel_id=body.channel_id,
            code=body.code, cart_subtotal_cents=body.cart_subtotal_cents,
            customer_id=body.customer_id,
            cart_lines=lines,
        )
    except DiscountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DiscountNotEligibleError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
