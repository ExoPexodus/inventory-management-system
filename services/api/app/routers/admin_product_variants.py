"""Admin endpoints for product variants."""
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
from app.models import Product, ProductVariant

router = APIRouter(
    prefix="/v1/admin/products",
    tags=["Product Variants"],
    dependencies=[require_permission("catalog:write")],
)


class VariantIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    options: dict = Field(default_factory=dict)
    unit_price_cents: int = Field(ge=0)
    status: str = "active"
    barcode: str | None = None
    image_url: str | None = None
    sort_order: int = 0


class VariantPatch(BaseModel):
    name: str | None = None
    options: dict | None = None
    unit_price_cents: int | None = Field(default=None, ge=0)
    status: str | None = None
    barcode: str | None = None
    image_url: str | None = None
    sort_order: int | None = None


class VariantOut(BaseModel):
    id: UUID
    product_id: UUID
    tenant_id: UUID
    sku: str
    name: str
    options: dict
    unit_price_cents: int
    status: str
    barcode: str | None
    image_url: str | None
    sort_order: int
    created_at: datetime
    model_config = {"from_attributes": True}


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_product_or_404(db: Session, product_id: UUID, tenant_id: UUID) -> Product:
    p = db.get(Product, product_id)
    if p is None or p.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Product not found")
    return p


def _get_variant_or_404(db: Session, variant_id: UUID, product_id: UUID, tenant_id: UUID) -> ProductVariant:
    v = db.get(ProductVariant, variant_id)
    if v is None or v.product_id != product_id or v.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Variant not found")
    return v


@router.get("/{product_id}/variants", response_model=list[VariantOut])
def list_variants(
    product_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[ProductVariant]:
    tenant_id = _require_tenant(ctx)
    _get_product_or_404(db, product_id, tenant_id)
    return list(db.execute(
        select(ProductVariant)
        .where(ProductVariant.product_id == product_id, ProductVariant.tenant_id == tenant_id)
        .order_by(ProductVariant.sort_order, ProductVariant.created_at)
    ).scalars().all())


@router.post("/{product_id}/variants", response_model=VariantOut, status_code=status.HTTP_201_CREATED)
def create_variant(
    product_id: UUID,
    body: VariantIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductVariant:
    tenant_id = _require_tenant(ctx)
    _get_product_or_404(db, product_id, tenant_id)
    variant = ProductVariant(
        tenant_id=tenant_id,
        product_id=product_id,
        **body.model_dump(),
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)
    return variant


@router.patch("/{product_id}/variants/{variant_id}", response_model=VariantOut)
def patch_variant(
    product_id: UUID,
    variant_id: UUID,
    body: VariantPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductVariant:
    tenant_id = _require_tenant(ctx)
    variant = _get_variant_or_404(db, variant_id, product_id, tenant_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(variant, field, value)
    db.commit()
    db.refresh(variant)
    return variant


@router.delete("/{product_id}/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant(
    product_id: UUID,
    variant_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    variant = _get_variant_or_404(db, variant_id, product_id, tenant_id)
    db.delete(variant)
    db.commit()
