"""Storefront catalog: product listing and detail endpoints."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import Product, ProductImage
from app.routers.storefront.auth import StorefrontChannelDep

router = APIRouter(prefix="/v1/storefront", tags=["Storefront Catalog"])


class StorefrontProductOut(BaseModel):
    id: UUID
    name: str
    slug: str | None
    subtitle: str | None
    ribbon: str | None
    description: str | None
    short_description: str | None
    product_type: str
    status: str
    sku: str
    unit_price_cents: int
    discount_price_cents: int | None
    currency_code: str
    image_url: str | None
    tags: list[str] | None
    track_quantity: bool
    weight_grams: int | None
    shipping_class: str | None
    digital_files: list[dict] | None
    gift_card_amounts_cents: list[int] | None
    gift_card_expiry_months: int | None
    meta_title: str | None
    meta_description: str | None

    model_config = {"from_attributes": True}


class ProductListOut(BaseModel):
    items: list[StorefrontProductOut]
    total: int
    page: int
    per_page: int


def _to_out(product: Product, currency: str) -> StorefrontProductOut:
    return StorefrontProductOut(
        id=product.id,
        name=product.name,
        slug=product.slug,
        subtitle=product.subtitle,
        ribbon=product.ribbon,
        description=product.description,
        short_description=product.short_description,
        product_type=product.product_type,
        status=product.status,
        sku=product.sku,
        unit_price_cents=product.unit_price_cents,
        discount_price_cents=product.discount_price_cents,
        currency_code=currency,
        image_url=product.image_url or (product.images[0].url if product.images else None),
        tags=product.tags,
        track_quantity=product.track_quantity,
        weight_grams=product.weight_grams,
        shipping_class=product.shipping_class,
        digital_files=product.digital_files,
        gift_card_amounts_cents=product.gift_card_amounts_cents,
        gift_card_expiry_months=product.gift_card_expiry_months,
        meta_title=product.meta_title,
        meta_description=product.meta_description,
    )


@router.get("/products", response_model=ProductListOut)
def list_products(
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
    q: str | None = None,
    product_type: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> ProductListOut:
    base = select(Product).where(
        Product.tenant_id == channel.tenant_id,
        Product.status == "active",
    )
    if q and q.strip():
        like = f"%{q.strip()}%"
        base = base.where(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if product_type:
        base = base.where(Product.product_type == product_type)

    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()

    rows = db.execute(
        base.options(selectinload(Product.images))
        .order_by(Product.name).offset((page - 1) * per_page).limit(per_page)
    ).scalars().all()

    return ProductListOut(
        items=[_to_out(r, channel.currency_code) for r in rows],
        total=total, page=page, per_page=per_page,
    )


@router.get("/products/{product_slug_or_id}", response_model=StorefrontProductOut)
def get_product(
    product_slug_or_id: str,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> StorefrontProductOut:
    product = None
    try:
        uid = UUID(product_slug_or_id)
        product = db.execute(
            select(Product)
            .options(selectinload(Product.images))
            .where(
                Product.id == uid,
                Product.tenant_id == channel.tenant_id,
                Product.status == "active",
            )
        ).scalar_one_or_none()
    except ValueError:
        pass

    if product is None:
        product = db.execute(
            select(Product)
            .options(selectinload(Product.images))
            .where(
                Product.slug == product_slug_or_id,
                Product.tenant_id == channel.tenant_id,
                Product.status == "active",
            )
        ).scalar_one_or_none()

    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return _to_out(product, channel.currency_code)
