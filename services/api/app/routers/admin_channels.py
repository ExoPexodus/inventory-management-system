"""Admin endpoints for managing sales channels.

POS channels are auto-managed (one per shop, created at migration time and on
shop creation via channel_service.get_or_create_pos_channel). Other channel
types (manual / shopify / woocommerce / headless) can be created and deleted
via this API.

Auth: requires `channels:manage` permission. Granted to the system `owner`
role by the 20260507000001 migration.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.billing.deps import EntitlementsDep
from app.db.admin_deps_db import get_db_admin
from app.models import Channel, InventoryPool

router = APIRouter(
    prefix="/v1/admin/channels",
    tags=["Admin Channels"],
    dependencies=[require_permission("channels:manage")],
)


_NON_POS_TYPES = {"manual", "shopify", "woocommerce", "headless"}


class ChannelIn(BaseModel):
    type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    inventory_pool_id: UUID
    currency_code: str = Field(min_length=3, max_length=3)
    config: dict | None = None


class ChannelPatch(BaseModel):
    name: str | None = None
    status: str | None = None
    inventory_pool_id: UUID | None = None
    currency_code: str | None = None
    config: dict | None = None


class ChannelOut(BaseModel):
    id: UUID
    tenant_id: UUID
    type: str
    name: str
    status: str
    config: dict
    inventory_pool_id: UUID
    currency_code: str
    shop_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


@router.get("", response_model=list[ChannelOut])
def list_channels(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[Channel]:
    tenant_id = _require_tenant(ctx)
    rows = db.execute(
        select(Channel).where(Channel.tenant_id == tenant_id).order_by(Channel.type, Channel.name)
    ).scalars().all()
    return list(rows)


@router.post("", response_model=ChannelOut, status_code=status.HTTP_201_CREATED)
def create_channel(
    body: ChannelIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    ents: EntitlementsDep,
) -> Channel:
    tenant_id = _require_tenant(ctx)

    if body.type == "pos":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="POS channels are auto-created per shop and cannot be created via API",
        )
    if body.type not in _NON_POS_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown channel type: {body.type}. Allowed: {sorted(_NON_POS_TYPES)}",
        )

    pool = db.get(InventoryPool, body.inventory_pool_id)
    if pool is None or pool.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="inventory_pool_id does not exist or does not belong to this tenant",
        )

    current_count = db.execute(
        select(func.count(Channel.id)).where(Channel.tenant_id == tenant_id)
    ).scalar_one()
    limit = ents.limit("max_channels")
    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "plan_upgrade_required",
                "required_feature": "max_channels",
                "current_plan": ents.plan_codename,
                "current_count": current_count,
                "limit": limit,
            },
        )

    row = Channel(
        tenant_id=tenant_id,
        type=body.type,
        name=body.name,
        status="active",
        config=body.config or {},
        inventory_pool_id=body.inventory_pool_id,
        currency_code=body.currency_code.upper(),
        shop_id=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{channel_id}", response_model=ChannelOut)
def update_channel(
    channel_id: UUID,
    body: ChannelPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> Channel:
    tenant_id = _require_tenant(ctx)
    row = db.get(Channel, channel_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    if row.type == "pos":
        for forbidden in ("inventory_pool_id", "currency_code"):
            if getattr(body, forbidden) is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot change {forbidden} of a POS channel",
                )

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field == "currency_code" and value is not None:
            value = value.upper()
        if field == "config" and value is not None:
            value = {**(row.config or {}), **value}
        setattr(row, field, value)

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    row = db.get(Channel, channel_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    if row.type == "pos":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="POS channels are auto-managed and cannot be deleted via API. Delete the shop instead.",
        )
    db.delete(row)
    db.commit()
