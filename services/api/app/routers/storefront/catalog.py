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


class StorefrontImageOut(BaseModel):
    url: str
    alt_text: str | None
    sort_order: int

    model_config = {"from_attributes": True}


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
    images: list[StorefrontImageOut] | None = None
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


# Correlated scalar subquery: first gallery image URL per product (sort_order ASC).
# Used by list_products to avoid loading full galleries for every product on the page.
_first_image_subq = (
    select(ProductImage.url)
    .where(ProductImage.product_id == Product.id)
    .order_by(ProductImage.sort_order.asc(), ProductImage.created_at.asc())
    .limit(1)
    .correlate(Product)
    .scalar_subquery()
)


def _to_out_list(product: Product, currency: str, first_image_url: str | None) -> StorefrontProductOut:
    """Build a list-context response. images is always null to avoid over-fetching."""
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
        image_url=product.image_url or first_image_url,
        images=None,
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


def _to_out_detail(product: Product, currency: str) -> StorefrontProductOut:
    """Build a detail-context response. images is the full gallery sorted by sort_order."""
    gallery = [
        StorefrontImageOut(url=img.url, alt_text=img.alt_text, sort_order=img.sort_order)
        for img in product.images
    ]
    first_gallery_url = gallery[0].url if gallery else None
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
        image_url=product.image_url or first_gallery_url,
        images=gallery,
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
    base_where = [
        Product.tenant_id == channel.tenant_id,
        Product.status == "active",
    ]
    if q and q.strip():
        like = f"%{q.strip()}%"
        base_where.append(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if product_type:
        base_where.append(Product.product_type == product_type)

    total = db.execute(
        select(func.count(Product.id)).where(*base_where)
    ).scalar_one()

    rows = db.execute(
        select(Product, _first_image_subq.label("first_image_url"))
        .where(*base_where)
        .order_by(Product.name)
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    items = [_to_out_list(row[0], channel.currency_code, row[1]) for row in rows]
    return ProductListOut(items=items, total=total, page=page, per_page=per_page)


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

    return _to_out_detail(product, channel.currency_code)
