"""Hosted checkout: session management, payment intent, order completion, HTML page."""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import CartItem, Channel, CheckoutSession, Order, OrderLine, OrderPayment, Product
from app.routers.storefront.auth import StorefrontChannelDep
from app.services.customer_resolver import resolve_or_create_customer
from app.services.discount_service import (
    CartLine,
    DiscountNotEligibleError, DiscountNotFoundError,
    apply_discount, record_discount_use,
)
from app.services.payment_service import (
    PaymentNotConfiguredError, PaymentProviderError,
    create_payment_intent, verify_payment, verify_razorpay_signature,
)
from app.services.reservation_service import commit_reservation

router = APIRouter(tags=["Hosted Checkout"])

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

CHECKOUT_SESSION_TTL_MINUTES = 30


class CreateSessionIn(BaseModel):
    cart_token: str


class CreateSessionOut(BaseModel):
    session_token: str
    checkout_url: str
    expires_at: datetime


class PaymentIntentIn(BaseModel):
    customer_email: str = ""
    shipping_address: dict | None = None


class CompleteCheckoutIn(BaseModel):
    payment_intent_id: str | None = None
    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None
    razorpay_signature: str | None = None
    customer_email: str = ""


class CompleteCheckoutOut(BaseModel):
    status: str
    order_id: str
    redirect_url: str


class ApplyDiscountIn(BaseModel):
    code: str


class ApplyDiscountOut(BaseModel):
    code: str
    discount_name: str
    discount_cents: int
    subtotal_cents: int
    shipping_cents: int
    tax_cents: int
    total_cents: int


def _load_cart(db: Session, channel_id: UUID, cart_token: str) -> list[tuple]:
    return list(db.execute(
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.cart_token == cart_token, CartItem.channel_id == channel_id)
    ).all())


def _get_session_or_404(db: Session, session_token: str) -> CheckoutSession:
    session = db.execute(
        select(CheckoutSession).where(CheckoutSession.session_token == session_token)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Checkout session not found")
    if session.status in ("completed", "cancelled"):
        raise HTTPException(status_code=410, detail=f"Checkout session is {session.status}")
    if datetime.now(UTC) > session.expires_at:
        raise HTTPException(status_code=410, detail="Checkout session has expired")
    return session


def _create_order_from_session(db: Session, channel: Channel, session: CheckoutSession,
                                customer_email: str, payment_id: str, payment_provider: str) -> Order:
    customer_id = None
    if customer_email:
        cust = resolve_or_create_customer(db, channel.tenant_id, channel.id, email=customer_email)
        if cust:
            customer_id = cust.id

    rows = _load_cart(db, channel.id, session.cart_token)
    order = Order(
        tenant_id=channel.tenant_id, channel_id=channel.id, status="confirmed",
        customer_id=customer_id, customer_email=customer_email,
        subtotal_cents=session.subtotal_cents, discount_cents=session.discount_cents,
        tax_cents=session.tax_cents, shipping_cents=session.shipping_cents,
        total_cents=session.total_cents, currency_code=session.currency_code,
        shipping_address=session.shipping_address,
    )
    db.add(order)
    db.flush()

    for ci, prod in rows:
        db.add(OrderLine(
            tenant_id=channel.tenant_id, order_id=order.id,
            product_id=prod.id, title=prod.name, sku=prod.sku,
            quantity=ci.quantity,
            unit_price_cents=ci.unit_price_cents,
            line_total_cents=ci.unit_price_cents * ci.quantity,
        ))
        if ci.reservation_id:
            commit_reservation(db, ci.reservation_id)
        db.delete(ci)

    # Record payment
    db.add(OrderPayment(
        tenant_id=channel.tenant_id,
        order_id=order.id,
        provider=payment_provider,
        provider_ref=payment_id,
        method="card",
        amount_cents=session.total_cents,
        status="paid",
    ))

    if session.discount_code and session.discount_cents > 0:
        from app.models import Discount
        from sqlalchemy import func as sqlfunc
        discount_row = db.execute(
            select(Discount).where(
                Discount.tenant_id == channel.tenant_id,
                sqlfunc.upper(Discount.code) == session.discount_code.upper(),
            )
        ).scalar_one_or_none()
        if discount_row:
            record_discount_use(
                db,
                tenant_id=channel.tenant_id,
                discount_id=discount_row.id,
                discount_amount_cents=session.discount_cents,
                cart_token=session.cart_token,
                customer_id=customer_id,
                order_id=order.id,
            )

    session.status = "completed"
    session.order_id = order.id
    session.external_payment_id = payment_id
    session.payment_provider = payment_provider
    db.commit()

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

    return order


@router.post("/v1/checkout/{session_token}/apply-discount", response_model=ApplyDiscountOut)
def apply_discount_to_session(
    session_token: str,
    body: ApplyDiscountIn,
    db: Annotated[Session, Depends(get_db)],
) -> ApplyDiscountOut:
    session = _get_session_or_404(db, session_token)
    channel = db.get(Channel, session.channel_id)

    cart_rows = _load_cart(db, channel.id, session.cart_token)
    cart_lines = [
        CartLine(product_id=ci.product_id, quantity=ci.quantity, unit_price_cents=ci.unit_price_cents)
        for ci, _ in cart_rows
    ]

    try:
        result = apply_discount(
            db,
            tenant_id=channel.tenant_id,
            channel_id=channel.id,
            cart_subtotal_cents=session.subtotal_cents,
            cart_lines=cart_lines,
            code=body.code.strip(),
        )
    except DiscountNotFoundError:
        raise HTTPException(status_code=404, detail="Discount code not found or inactive")
    except DiscountNotEligibleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    session.discount_cents = result["discount_amount_cents"]
    session.discount_code = body.code.strip().upper()
    session.total_cents = max(
        0,
        session.subtotal_cents + session.shipping_cents + session.tax_cents - session.discount_cents,
    )
    db.commit()

    return ApplyDiscountOut(
        code=session.discount_code,
        discount_name=result["name"],
        discount_cents=session.discount_cents,
        subtotal_cents=session.subtotal_cents,
        shipping_cents=session.shipping_cents,
        tax_cents=session.tax_cents,
        total_cents=session.total_cents,
    )


@router.delete("/v1/checkout/{session_token}/discount", status_code=status.HTTP_204_NO_CONTENT)
def remove_discount_from_session(
    session_token: str,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    session = _get_session_or_404(db, session_token)
    session.discount_cents = 0
    session.discount_code = None
    session.total_cents = session.subtotal_cents + session.shipping_cents + session.tax_cents
    db.commit()


@router.post("/v1/storefront/checkout/session",
             response_model=CreateSessionOut, status_code=status.HTTP_201_CREATED)
def create_checkout_session(
    body: CreateSessionIn,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
    request: Request,
) -> CreateSessionOut:
    rows = _load_cart(db, channel.id, body.cart_token)
    if not rows:
        raise HTTPException(status_code=400, detail="Cart is empty")

    subtotal = sum(ci.unit_price_cents * ci.quantity for ci, _ in rows)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=CHECKOUT_SESSION_TTL_MINUTES)

    session = CheckoutSession(
        tenant_id=channel.tenant_id, channel_id=channel.id,
        cart_token=body.cart_token, session_token=token,
        status="pending", currency_code=channel.currency_code,
        subtotal_cents=subtotal, total_cents=subtotal, expires_at=expires_at,
    )
    db.add(session)
    db.commit()

    checkout_domain = (channel.config or {}).get("checkout_domain", "").strip()
    if checkout_domain:
        if not checkout_domain.startswith(("http://", "https://")):
            checkout_domain = f"https://{checkout_domain}"
        base_url = checkout_domain.rstrip("/")
    else:
        base_url = str(request.base_url).rstrip("/")
    return CreateSessionOut(
        session_token=token,
        checkout_url=f"{base_url}/checkout/{token}",
        expires_at=expires_at,
    )


@router.get("/checkout/{session_token}", response_class=HTMLResponse)
def checkout_page(
    session_token: str,
    db: Annotated[Session, Depends(get_db)],
    request: Request,
) -> HTMLResponse:
    session = _get_session_or_404(db, session_token)
    channel = db.get(Channel, session.channel_id)
    if channel is None:
        raise HTTPException(status_code=404)

    rows = _load_cart(db, channel.id, session.cart_token)
    cart_items = [
        {"product_name": prod.name, "quantity": ci.quantity,
         "line_total_cents": ci.unit_price_cents * ci.quantity,
         "currency_code": ci.currency_code}
        for ci, prod in rows
    ]
    provider = channel.config.get("payment_provider", "none")
    pub_key = channel.config.get("stripe_publishable_key", "") or channel.config.get("razorpay_key_id", "")

    return templates.TemplateResponse(request, "checkout.html", {
        "session_token": session_token,
        "cart_items": cart_items,
        "subtotal_cents": session.subtotal_cents,
        "shipping_cents": session.shipping_cents,
        "tax_cents": session.tax_cents,
        "discount_cents": session.discount_cents,
        "discount_code": session.discount_code or "",
        "total_cents": session.total_cents,
        "currency_code": session.currency_code,
        "provider": provider,
        "publishable_key": pub_key,
    })


@router.post("/v1/checkout/{session_token}/payment-intent")
def create_session_payment_intent(
    session_token: str,
    body: PaymentIntentIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    session = _get_session_or_404(db, session_token)
    channel = db.get(Channel, session.channel_id)

    if body.customer_email:
        session.customer_email = body.customer_email
    if body.shipping_address:
        session.shipping_address = body.shipping_address

    try:
        result = create_payment_intent(channel, session.total_cents, session.currency_code)
    except PaymentNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PaymentProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    session.external_payment_id = result.get("payment_intent_id") or result.get("order_id")
    session.status = "payment_initiated"
    session.payment_provider = result["provider"]
    db.commit()
    return result


@router.post("/v1/checkout/{session_token}/complete", response_model=CompleteCheckoutOut)
def complete_checkout(
    session_token: str,
    body: CompleteCheckoutIn,
    db: Annotated[Session, Depends(get_db)],
    request: Request,
) -> CompleteCheckoutOut:
    session = _get_session_or_404(db, session_token)
    channel = db.get(Channel, session.channel_id)
    provider = session.payment_provider or channel.config.get("payment_provider", "none")

    verified = False
    payment_id = ""
    if provider == "stripe" and body.payment_intent_id:
        verified = verify_payment(channel, body.payment_intent_id)
        payment_id = body.payment_intent_id
    elif provider == "razorpay" and body.razorpay_order_id:
        verified = verify_razorpay_signature(
            channel, body.razorpay_order_id,
            body.razorpay_payment_id or "", body.razorpay_signature or "",
        )
        payment_id = body.razorpay_payment_id or ""

    if not verified:
        raise HTTPException(status_code=400, detail="Payment verification failed")

    order = _create_order_from_session(
        db, channel, session,
        customer_email=body.customer_email or session.customer_email or "",
        payment_id=payment_id, payment_provider=provider,
    )

    success_url = channel.config.get("checkout_success_url", "")
    redirect_url = f"{success_url}?order_id={order.id}" if success_url else str(request.base_url)
    return CompleteCheckoutOut(status="completed", order_id=str(order.id), redirect_url=redirect_url)


@router.get("/checkout/{session_token}/stripe-return")
def stripe_return(
    session_token: str,
    db: Annotated[Session, Depends(get_db)],
    request: Request,
    payment_intent: str | None = None,
    redirect_status: str | None = None,
) -> RedirectResponse:
    if redirect_status != "succeeded" or not payment_intent:
        return RedirectResponse(url=f"/checkout/{session_token}?error=payment_failed")

    try:
        session = _get_session_or_404(db, session_token)
    except HTTPException:
        return RedirectResponse(url="/")

    channel = db.get(Channel, session.channel_id)
    if not verify_payment(channel, payment_intent):
        return RedirectResponse(url=f"/checkout/{session_token}?error=payment_failed")

    order = _create_order_from_session(
        db, channel, session,
        customer_email=session.customer_email or "",
        payment_id=payment_intent, payment_provider="stripe",
    )
    success_url = channel.config.get("checkout_success_url", "")
    return RedirectResponse(url=f"{success_url}?order_id={order.id}" if success_url else "/")
