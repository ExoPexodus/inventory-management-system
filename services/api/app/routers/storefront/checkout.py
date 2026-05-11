"""Storefront checkout: summary, discount apply, Path-2 order submission."""
from __future__ import annotations

import uuid
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import CartItem, Order, OrderLine, OrderPayment, Product
from app.routers.storefront.auth import StorefrontChannelDep
from app.services.customer_resolver import resolve_or_create_customer
from app.services.discount_service import (
    CartLine,
    DiscountNotEligibleError, DiscountNotFoundError, apply_discount,
)
from app.services.reservation_service import commit_reservation

router = APIRouter(prefix="/v1/storefront", tags=["Storefront Checkout"])


class CartSummaryOut(BaseModel):
    cart_token: str
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    shipping_cents: int
    total_cents: int
    currency_code: str
    discount_code: str | None


class DiscountApplyIn(BaseModel):
    code: str


class DiscountApplyOut(BaseModel):
    cart_token: str
    discount_code: str
    discount_type: str
    discount_cents: int
    final_subtotal_cents: int
    is_free_shipping: bool


class SubmitOrderIn(BaseModel):
    cart_token: str
    payment_provider: str
    payment_reference: str
    customer_email: str | None = None
    customer_phone: str | None = None
    shipping_address: dict | None = None
    billing_address: dict | None = None
    discount_code: str | None = None


class OrderOut(BaseModel):
    id: str
    channel_id: str
    status: str
    customer_email: str | None
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    shipping_cents: int
    total_cents: int
    currency_code: str


def _cart_subtotal(db: Session, channel_id: UUID, cart_token: str) -> tuple[int, list[tuple]]:
    rows = db.execute(
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.cart_token == cart_token, CartItem.channel_id == channel_id)
    ).all()
    subtotal = sum(ci.unit_price_cents * ci.quantity for ci, _ in rows)
    return subtotal, list(rows)


@router.get("/cart/{cart_token}/summary", response_model=CartSummaryOut)
def cart_summary(
    cart_token: str,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
    destination_country: str | None = Query(default=None),
    destination_state: str | None = Query(default=None),
    discount_code: str | None = Query(default=None),
) -> CartSummaryOut:
    subtotal, rows = _cart_subtotal(db, channel.id, cart_token)
    if not rows:
        return CartSummaryOut(
            cart_token=cart_token, subtotal_cents=0, discount_cents=0,
            tax_cents=0, shipping_cents=0, total_cents=0,
            currency_code=channel.currency_code, discount_code=None,
        )

    discount_cents = 0
    applied_code = None
    if discount_code:
        try:
            lines = [
                CartLine(product_id=ci.product_id, quantity=ci.quantity, unit_price_cents=ci.unit_price_cents)
                for ci, _ in rows
            ]
            result = apply_discount(
                db, tenant_id=channel.tenant_id, channel_id=channel.id,
                code=discount_code, cart_subtotal_cents=subtotal,
                cart_lines=lines,
            )
            discount_cents = result["discount_amount_cents"]
            applied_code = discount_code
        except (DiscountNotFoundError, DiscountNotEligibleError):
            pass

    tax_cents = 0
    if destination_country:
        try:
            from app.services.tax_service import calculate_tax_for_cart
            cart_lines = [
                {"product_id": ci.product_id, "quantity": ci.quantity,
                 "unit_price_cents": ci.unit_price_cents}
                for ci, _ in rows
            ]
            tax_result = calculate_tax_for_cart(
                db, channel_id=channel.id,
                destination_country=destination_country,
                destination_state=destination_state,
                cart_lines=cart_lines,
                currency=channel.currency_code,
            )
            tax_cents = tax_result["total_tax_cents"]
        except Exception:
            pass

    total = (subtotal - discount_cents) + tax_cents
    return CartSummaryOut(
        cart_token=cart_token, subtotal_cents=subtotal, discount_cents=discount_cents,
        tax_cents=tax_cents, shipping_cents=0, total_cents=total,
        currency_code=channel.currency_code, discount_code=applied_code,
    )


@router.post("/cart/{cart_token}/discount", response_model=DiscountApplyOut)
def apply_cart_discount(
    cart_token: str,
    body: DiscountApplyIn,
    request: Request,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> DiscountApplyOut:
    from app.services.storefront_rate_limits import (
        check_discount_rate_limit, record_discount_attempt,
    )

    client_ip = (request.client.host if request.client else None) or "unknown"
    # Block further attempts before the lookup — stops enumeration even if
    # the attacker is rotating valid candidate codes.
    check_discount_rate_limit(client_ip, channel.id)

    subtotal, cart_rows = _cart_subtotal(db, channel.id, cart_token)
    lines = [
        CartLine(product_id=ci.product_id, quantity=ci.quantity, unit_price_cents=ci.unit_price_cents)
        for ci, _ in cart_rows
    ]
    try:
        result = apply_discount(
            db, tenant_id=channel.tenant_id, channel_id=channel.id,
            code=body.code, cart_subtotal_cents=subtotal,
            cart_lines=lines,
        )
    except DiscountNotFoundError as exc:
        record_discount_attempt(client_ip, channel.id, success=False)
        raise HTTPException(status_code=404, detail=str(exc))
    except DiscountNotEligibleError as exc:
        # An eligible-but-wrong-cart attempt isn't enumeration — the code
        # WAS valid. Don't count toward the lockout.
        raise HTTPException(status_code=422, detail=str(exc))

    record_discount_attempt(client_ip, channel.id, success=True)
    return DiscountApplyOut(
        cart_token=cart_token, discount_code=body.code,
        discount_type=result["discount_type"],
        discount_cents=result["discount_amount_cents"],
        final_subtotal_cents=result["final_total_cents"],
        is_free_shipping=result["is_free_shipping"],
    )


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def submit_order(
    body: SubmitOrderIn,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> OrderOut:
    subtotal, rows = _cart_subtotal(db, channel.id, body.cart_token)
    if not rows:
        raise HTTPException(status_code=400, detail="Cart is empty")

    discount_cents = 0
    if body.discount_code:
        try:
            order_lines = [
                CartLine(product_id=ci.product_id, quantity=ci.quantity, unit_price_cents=ci.unit_price_cents)
                for ci, _ in rows
            ]
            dr = apply_discount(
                db, tenant_id=channel.tenant_id, channel_id=channel.id,
                code=body.discount_code, cart_subtotal_cents=subtotal,
                cart_lines=order_lines,
            )
            discount_cents = dr["discount_amount_cents"]
        except (DiscountNotFoundError, DiscountNotEligibleError):
            pass

    total = subtotal - discount_cents

    customer_id = None
    if body.customer_email or body.customer_phone:
        cust = resolve_or_create_customer(
            db, channel.tenant_id, channel.id,
            email=body.customer_email, phone=body.customer_phone,
        )
        if cust:
            customer_id = cust.id

    order = Order(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        status="confirmed",
        customer_id=customer_id,
        customer_email=body.customer_email,
        customer_phone=body.customer_phone,
        subtotal_cents=subtotal,
        discount_cents=discount_cents,
        tax_cents=0,
        shipping_cents=0,
        total_cents=total,
        currency_code=channel.currency_code,
        shipping_address=body.shipping_address,
        billing_address=body.billing_address,
    )
    db.add(order)
    db.flush()

    for cart_item, product in rows:
        db.add(OrderLine(
            tenant_id=channel.tenant_id,
            order_id=order.id,
            product_id=product.id,
            title=product.name,
            sku=product.sku,
            quantity=cart_item.quantity,
            unit_price_cents=cart_item.unit_price_cents,
            line_total_cents=cart_item.unit_price_cents * cart_item.quantity,
        ))
        if cart_item.reservation_id:
            commit_reservation(db, cart_item.reservation_id)
        db.delete(cart_item)

    db.add(OrderPayment(
        tenant_id=channel.tenant_id,
        order_id=order.id,
        provider=body.payment_provider,
        provider_ref=body.payment_reference,
        method="card",
        amount_cents=total,
        status="paid",
    ))

    db.commit()
    db.refresh(order)

    from app.services.email_service import send_order_confirmation
    send_order_confirmation(db, order)

    from app.services.webhook_service import build_order_confirmed_payload, fire_event
    fire_event(db, channel.tenant_id, "order.confirmed",
               build_order_confirmed_payload(db, order))

    # Enqueue shipping dispatch if channel has a provider configured
    try:
        from app.services.shipping.registry import get_channel_provider
        from app.services.shipping.base import ShippingNotConfiguredError
        get_channel_provider(channel)
        from app.worker.queue import task_queue
        task_queue().enqueue(
            "app.worker.tasks.dispatch_shipment",
            str(order.id),
            job_timeout=120,
        )
    except ShippingNotConfiguredError:
        pass  # No shipping provider configured — skip silently
    except Exception:
        import logging as _log
        _log.getLogger(__name__).warning(
            "Failed to enqueue dispatch for order %s", order.id, exc_info=True
        )

    return OrderOut(
        id=str(order.id),
        channel_id=str(order.channel_id),
        status=order.status,
        customer_email=order.customer_email,
        subtotal_cents=order.subtotal_cents,
        discount_cents=order.discount_cents,
        tax_cents=order.tax_cents,
        shipping_cents=order.shipping_cents,
        total_cents=order.total_cents,
        currency_code=order.currency_code,
    )
