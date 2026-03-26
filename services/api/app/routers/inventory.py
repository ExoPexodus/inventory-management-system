from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.db.admin_deps_db import get_db_admin
from app.models import Product, ProductGroup, Shop
from app.services.stock import current_quantity

router = APIRouter(prefix="/v1/inventory", tags=["Inventory"])


class ProductInventoryOut(BaseModel):
    product_id: UUID
    sku: str
    name: str
    unit_price_cents: int
    quantity: int
    product_group_id: UUID | None = None
    group_title: str | None = None
    variant_label: str | None = None


class UpdatePriceBody(BaseModel):
    unit_price_cents: int = Field(ge=0)


@router.get("/shop/{shop_id}/products", response_model=list[ProductInventoryOut])
def shop_inventory(
    shop_id: UUID,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[ProductInventoryOut]:
    shop = db.get(Shop, shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    prods = db.execute(
        select(Product).where(Product.tenant_id == shop.tenant_id, Product.active.is_(True))
    ).scalars().all()
    gids = {p.product_group_id for p in prods if p.product_group_id is not None}
    titles: dict[UUID, str] = {}
    if gids:
        for g in db.execute(select(ProductGroup).where(ProductGroup.id.in_(gids))).scalars().all():
            titles[g.id] = g.title
    return [
        ProductInventoryOut(
            product_id=p.id,
            sku=p.sku,
            name=p.name,
            unit_price_cents=p.unit_price_cents,
            quantity=current_quantity(db, shop_id, p.id),
            product_group_id=p.product_group_id,
            group_title=titles.get(p.product_group_id) if p.product_group_id else None,
            variant_label=p.variant_label,
        )
        for p in prods
    ]


@router.patch("/products/{product_id}/price", response_model=ProductInventoryOut)
def update_product_price(
    product_id: UUID,
    body: UpdatePriceBody,
    _: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductInventoryOut:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    product.unit_price_cents = body.unit_price_cents
    db.commit()
    gt: str | None = None
    if product.product_group_id is not None:
        grp = db.get(ProductGroup, product.product_group_id)
        gt = grp.title if grp else None
    return ProductInventoryOut(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        unit_price_cents=product.unit_price_cents,
        quantity=0,
        product_group_id=product.product_group_id,
        group_title=gt,
        variant_label=product.variant_label,
    )

