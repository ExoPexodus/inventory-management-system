"""Storefront cart: create, read, add/update/remove items with reservation management."""
from __future__ import annotations

import uuid
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import CartItem, Product
from app.routers.storefront.auth import StorefrontChannelDep
from app.services.inventory_pool_service import pool_shops
from app.services.product_type_service import is_inventory_tracked
from app.services.reservation_service import release_reservation, reserve
from app.services.storefront_rate_limits import check_cart_creation_rate

router = APIRouter(prefix="/v1/storefront", tags=["Storefront Cart"])


class AddItemIn(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)


class CartItemOut(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    unit_price_cents: int
    line_total_cents: int
    currency_code: str


class CartOut(BaseModel):
    cart_token: str
    channel_id: UUID
    items: list[CartItemOut]
    subtotal_cents: int
    total_cents: int
    currency_code: str


def _load_cart(db: Session, channel_id: UUID, cart_token: str) -> CartOut:
    from app.models import Channel
    channel = db.get(Channel, channel_id)
    rows = db.execute(
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.cart_token == cart_token, CartItem.channel_id == channel_id)
        .order_by(CartItem.created_at)
    ).all()

    items = [
        CartItemOut(
            id=ci.id,
            product_id=ci.product_id,
            product_name=prod.name,
            quantity=ci.quantity,
            unit_price_cents=ci.unit_price_cents,
            line_total_cents=ci.unit_price_cents * ci.quantity,
            currency_code=ci.currency_code,
        )
        for ci, prod in rows
    ]
    subtotal = sum(i.line_total_cents for i in items)
    currency = channel.currency_code if channel else "USD"
    return CartOut(
        cart_token=cart_token, channel_id=channel_id,
        items=items, subtotal_cents=subtotal, total_cents=subtotal,
        currency_code=currency,
    )


def _get_shop_for_channel(db: Session, channel) -> UUID | None:
    shop_ids = pool_shops(db, channel.inventory_pool_id)
    return shop_ids[0] if shop_ids else None


@router.post("/cart", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def create_cart(
    request: Request,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> CartOut:
    client_ip = (request.client.host if request.client else None) or "unknown"
    check_cart_creation_rate(client_ip, channel.id)
    token = str(uuid.uuid4())
    return CartOut(
        cart_token=token, channel_id=channel.id,
        items=[], subtotal_cents=0, total_cents=0,
        currency_code=channel.currency_code,
    )


@router.get("/cart/{cart_token}", response_model=CartOut)
def get_cart(
    cart_token: str,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> CartOut:
    return _load_cart(db, channel.id, cart_token)


@router.post("/cart/{cart_token}/items", response_model=CartOut)
def add_or_update_item(
    cart_token: str,
    body: AddItemIn,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> CartOut:
    product = db.execute(
        select(Product).where(
            Product.id == body.product_id,
            Product.tenant_id == channel.tenant_id,
            Product.status == "active",
        )
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Product not found or inactive")

    unit_price = product.unit_price_cents
    try:
        from app.billing.pricing import price_for_product_in_currency
        p = price_for_product_in_currency(db, product.id, channel.currency_code,
                                          channel_id=channel.id)
        unit_price = p.amount_cents
    except Exception:
        pass

    existing = db.execute(
        select(CartItem).where(
            CartItem.cart_token == cart_token,
            CartItem.product_id == body.product_id,
            CartItem.channel_id == channel.id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.quantity = body.quantity
        existing.unit_price_cents = unit_price
        item = existing
    else:
        item = CartItem(
            tenant_id=channel.tenant_id,
            channel_id=channel.id,
            cart_token=cart_token,
            product_id=body.product_id,
            quantity=body.quantity,
            unit_price_cents=unit_price,
            currency_code=channel.currency_code,
        )
        db.add(item)
    db.flush()

    if is_inventory_tracked(product.product_type, track_quantity=product.track_quantity):
        shop_id = _get_shop_for_channel(db, channel)
        if shop_id:
            res = reserve(
                db,
                tenant_id=channel.tenant_id,
                channel_id=channel.id,
                product_id=product.id,
                shop_id=shop_id,
                quantity=body.quantity,
                cart_token=cart_token,
                purpose="cart",
            )
            item.reservation_id = res.id
            db.flush()

    db.commit()
    return _load_cart(db, channel.id, cart_token)


@router.delete("/cart/{cart_token}/items/{item_id}", response_model=CartOut)
def remove_item(
    cart_token: str,
    item_id: UUID,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> CartOut:
    item = db.execute(
        select(CartItem).where(
            CartItem.id == item_id,
            CartItem.cart_token == cart_token,
            CartItem.channel_id == channel.id,
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

    if item.reservation_id:
        release_reservation(db, item.reservation_id)

    db.delete(item)
    db.commit()
    return _load_cart(db, channel.id, cart_token)
