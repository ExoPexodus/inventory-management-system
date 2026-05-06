"""Admin endpoints for managing inventory pools and pool ↔ shop membership."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import InventoryPool, InventoryPoolShop, Shop

router = APIRouter(
    prefix="/v1/admin/inventory-pools",
    tags=["Admin Inventory Pools"],
    dependencies=[require_permission("inventory_pools:manage")],
)


_FULFILLMENT_POLICIES = {"fulfill_from_primary", "split_proportionally", "manual_at_fulfillment"}


class InventoryPoolIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    fulfillment_policy: str = "fulfill_from_primary"
    shop_ids: list[UUID] = Field(default_factory=list)


class InventoryPoolPatch(BaseModel):
    name: str | None = None
    fulfillment_policy: str | None = None
    shop_ids: list[UUID] | None = None


class InventoryPoolOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    fulfillment_policy: str
    shop_ids: list[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _serialize(db: Session, pool: InventoryPool) -> InventoryPoolOut:
    shop_ids = db.execute(
        select(InventoryPoolShop.shop_id).where(InventoryPoolShop.pool_id == pool.id)
    ).scalars().all()
    return InventoryPoolOut(
        id=pool.id,
        tenant_id=pool.tenant_id,
        name=pool.name,
        fulfillment_policy=pool.fulfillment_policy,
        shop_ids=list(shop_ids),
        created_at=pool.created_at,
        updated_at=pool.updated_at,
    )


def _validate_shop_ids(db: Session, tenant_id: UUID, shop_ids: list[UUID]) -> None:
    if not shop_ids:
        return
    rows = db.execute(
        select(Shop.id).where(Shop.id.in_(shop_ids), Shop.tenant_id == tenant_id)
    ).scalars().all()
    found = set(rows)
    requested = set(shop_ids)
    missing = requested - found
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"shop_ids do not belong to this tenant: {sorted(str(m) for m in missing)}",
        )


def _replace_pool_membership(
    db: Session, tenant_id: UUID, pool_id: UUID, shop_ids: list[UUID]
) -> None:
    db.execute(
        InventoryPoolShop.__table__.delete().where(InventoryPoolShop.pool_id == pool_id)
    )
    for sid in shop_ids:
        db.add(InventoryPoolShop(tenant_id=tenant_id, pool_id=pool_id, shop_id=sid))


@router.get("", response_model=list[InventoryPoolOut])
def list_pools(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[InventoryPoolOut]:
    tenant_id = _require_tenant(ctx)
    pools = db.execute(
        select(InventoryPool).where(InventoryPool.tenant_id == tenant_id).order_by(InventoryPool.name)
    ).scalars().all()
    return [_serialize(db, p) for p in pools]


@router.post("", response_model=InventoryPoolOut, status_code=status.HTTP_201_CREATED)
def create_pool(
    body: InventoryPoolIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> InventoryPoolOut:
    tenant_id = _require_tenant(ctx)

    if body.fulfillment_policy not in _FULFILLMENT_POLICIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid fulfillment_policy. Allowed: {sorted(_FULFILLMENT_POLICIES)}",
        )

    _validate_shop_ids(db, tenant_id, body.shop_ids)

    pool = InventoryPool(
        tenant_id=tenant_id,
        name=body.name,
        fulfillment_policy=body.fulfillment_policy,
    )
    db.add(pool)
    db.flush()

    for sid in body.shop_ids:
        db.add(InventoryPoolShop(tenant_id=tenant_id, pool_id=pool.id, shop_id=sid))

    db.commit()
    db.refresh(pool)
    return _serialize(db, pool)


@router.patch("/{pool_id}", response_model=InventoryPoolOut)
def update_pool(
    pool_id: UUID,
    body: InventoryPoolPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> InventoryPoolOut:
    tenant_id = _require_tenant(ctx)
    pool = db.get(InventoryPool, pool_id)
    if pool is None or pool.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Pool not found")

    if body.fulfillment_policy is not None:
        if body.fulfillment_policy not in _FULFILLMENT_POLICIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid fulfillment_policy. Allowed: {sorted(_FULFILLMENT_POLICIES)}",
            )
        pool.fulfillment_policy = body.fulfillment_policy

    if body.name is not None:
        pool.name = body.name

    if body.shop_ids is not None:
        _validate_shop_ids(db, tenant_id, body.shop_ids)
        _replace_pool_membership(db, tenant_id, pool.id, body.shop_ids)

    db.commit()
    db.refresh(pool)
    return _serialize(db, pool)


@router.delete("/{pool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pool(
    pool_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    pool = db.get(InventoryPool, pool_id)
    if pool is None or pool.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Pool not found")

    try:
        db.delete(pool)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Pool is in use by one or more channels and cannot be deleted",
        )
