"""Admin catalog endpoints: product detail view and image gallery management.

The existing CRUD endpoints (create/list/patch products) live in admin_web.py
for backwards compat. This router adds:
  - GET  /v1/admin/catalog/products/{id}                   — full product detail
  - GET  /v1/admin/catalog/products/{id}/images            — list images
  - POST /v1/admin/catalog/products/{id}/images            — add an image
  - DELETE /v1/admin/catalog/products/{id}/images/{image_id} — remove an image

Auth: requires catalog:read or catalog:write.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Category, Product, ProductCategory, ProductImage

router = APIRouter(prefix="/v1/admin/catalog", tags=["Admin Catalog"])


class ProductImageOut(BaseModel):
    id: UUID
    tenant_id: UUID
    product_id: UUID
    url: str
    alt_text: str | None
    sort_order: int
    file_size_bytes: int | None = None
    created_at: datetime
    model_config = {"from_attributes": True}


class ProductImageIn(BaseModel):
    url: str = Field(min_length=1, max_length=1024)
    alt_text: str | None = Field(default=None, max_length=255)
    sort_order: int = 0
    file_size_bytes: int | None = Field(default=None, ge=1)


class ProductDetailOut(BaseModel):
    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    product_type: str
    status: str
    unit_price_cents: int
    discount_price_cents: int | None
    subtitle: str | None
    ribbon: str | None
    short_description: str | None
    description: str | None
    tags: list[str] | None
    track_quantity: bool
    weight_grams: int | None
    shipping_class: str | None
    digital_files: list[dict] | None
    gift_card_amounts_cents: list[int] | None
    gift_card_expiry_months: int | None
    additional_info_sections: list[dict] | None
    slug: str | None
    meta_title: str | None
    meta_description: str | None
    og_image_url: str | None
    image_url: str | None
    images: list[ProductImageOut]
    category_slugs: list[str] = []
    product_group_id: UUID | None
    cost_price_cents: int | None
    mrp_cents: int | None
    barcode: str | None
    hsn_code: str | None
    negative_inventory_allowed: bool
    reorder_point: int
    created_at: datetime

    model_config = {"from_attributes": True}


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


def _get_product_or_404(db: Session, product_id: UUID, tenant_id: UUID) -> Product:
    product = db.execute(
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.id == product_id, Product.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.get(
    "/products/{product_id}",
    response_model=ProductDetailOut,
    dependencies=[require_permission("catalog:read")],
)
def get_product_detail(
    product_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductDetailOut:
    tenant_id = _require_tenant(ctx)
    product = _get_product_or_404(db, product_id, tenant_id)
    slugs = list(
        db.execute(
            select(Category.slug)
            .join(ProductCategory, ProductCategory.category_id == Category.id)
            .where(ProductCategory.product_id == product_id, Category.tenant_id == tenant_id)
            .order_by(Category.sort_order, Category.name)
        ).scalars().all()
    )
    return ProductDetailOut.model_validate({
        **{c.name: getattr(product, c.name) for c in Product.__table__.columns},
        "images": product.images,
        "category_slugs": slugs,
    })


@router.get(
    "/products/{product_id}/images",
    response_model=list[ProductImageOut],
    dependencies=[require_permission("catalog:read")],
)
def list_product_images(
    product_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[ProductImage]:
    tenant_id = _require_tenant(ctx)
    _get_product_or_404(db, product_id, tenant_id)
    rows = db.execute(
        select(ProductImage)
        .where(ProductImage.product_id == product_id)
        .order_by(ProductImage.sort_order, ProductImage.created_at)
    ).scalars().all()
    return list(rows)


@router.post(
    "/products/{product_id}/images",
    response_model=ProductImageOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("catalog:write")],
)
def add_product_image(
    product_id: UUID,
    body: ProductImageIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductImage:
    from sqlalchemy import update as sa_update
    from app.models import Tenant as TenantModel
    tenant_id = _require_tenant(ctx)
    _get_product_or_404(db, product_id, tenant_id)

    img = ProductImage(
        tenant_id=tenant_id,
        product_id=product_id,
        url=body.url,
        alt_text=body.alt_text,
        sort_order=body.sort_order,
        file_size_bytes=body.file_size_bytes,
    )
    db.add(img)
    db.flush()

    if body.file_size_bytes is not None:
        tenant = db.get(TenantModel, tenant_id)
        if tenant and tenant.storage_mode == "platform":
            db.execute(
                sa_update(TenantModel)
                .where(TenantModel.id == tenant_id)
                .values(storage_bytes_used=TenantModel.storage_bytes_used + body.file_size_bytes)
            )

    db.commit()
    db.refresh(img)
    return img


@router.delete(
    "/products/{product_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("catalog:write")],
)
def delete_product_image(
    product_id: UUID,
    image_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    from sqlalchemy import update as sa_update
    from app.models import Tenant as TenantModel
    tenant_id = _require_tenant(ctx)
    _get_product_or_404(db, product_id, tenant_id)

    img = db.get(ProductImage, image_id)
    if img is None or img.product_id != product_id or img.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    file_size = img.file_size_bytes
    db.delete(img)
    db.flush()

    if file_size is not None:
        tenant = db.get(TenantModel, tenant_id)
        if tenant and tenant.storage_mode == "platform":
            db.execute(
                sa_update(TenantModel)
                .where(TenantModel.id == tenant_id)
                .values(storage_bytes_used=TenantModel.storage_bytes_used - file_size)
            )

    db.commit()
