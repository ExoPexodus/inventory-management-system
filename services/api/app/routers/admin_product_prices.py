"""Admin endpoints for per-product, per-currency, optionally per-channel pricing.

Routes nested under /v1/admin/products/{product_id}/prices.
Auth: requires `currency:manage` permission.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Channel, Product, ProductPrice

router = APIRouter(
    prefix="/v1/admin/products",
    tags=["Admin Product Prices"],
    dependencies=[require_permission("currency:manage")],
)


class ProductPriceIn(BaseModel):
    channel_id: UUID | None = None
    currency_code: str = Field(min_length=3, max_length=3)
    amount_cents: int = Field(ge=0)


class ProductPriceOut(BaseModel):
    id: UUID
    tenant_id: UUID
    product_id: UUID
    channel_id: UUID | None
    currency_code: str
    amount_cents: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _require_tenant_and_product(ctx: AdminAuthDep, db: Session, product_id: UUID) -> tuple[UUID, Product]:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    product = db.get(Product, product_id)
    if product is None or product.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ctx.tenant_id, product


@router.get("/{product_id}/prices", response_model=list[ProductPriceOut])
def list_prices(
    product_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[ProductPrice]:
    tenant_id, product = _require_tenant_and_product(ctx, db, product_id)
    rows = db.execute(
        select(ProductPrice).where(
            ProductPrice.product_id == product_id,
        ).order_by(ProductPrice.currency_code, ProductPrice.channel_id)
    ).scalars().all()
    return list(rows)


@router.post("/{product_id}/prices", response_model=ProductPriceOut, status_code=status.HTTP_201_CREATED)
def create_or_update_price(
    product_id: UUID,
    body: ProductPriceIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductPrice:
    tenant_id, product = _require_tenant_and_product(ctx, db, product_id)

    if body.channel_id is not None:
        ch = db.get(Channel, body.channel_id)
        if ch is None or ch.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="channel_id does not belong to this tenant",
            )

    currency = body.currency_code.upper()

    existing = db.execute(
        select(ProductPrice).where(
            ProductPrice.product_id == product_id,
            ProductPrice.channel_id == body.channel_id,
            ProductPrice.currency_code == currency,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.amount_cents = body.amount_cents
        row = existing
    else:
        row = ProductPrice(
            tenant_id=tenant_id,
            product_id=product_id,
            channel_id=body.channel_id,
            currency_code=currency,
            amount_cents=body.amount_cents,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{product_id}/prices/{price_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_price(
    product_id: UUID,
    price_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id, product = _require_tenant_and_product(ctx, db, product_id)
    row = db.get(ProductPrice, price_id)
    if row is None or row.tenant_id != tenant_id or row.product_id != product_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price not found")
    db.delete(row)
    db.commit()
