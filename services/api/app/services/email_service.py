from __future__ import annotations

import base64
import json
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib import request
from uuid import UUID

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Order, OrderLine, TenantEmailConfig

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "email_templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)

_RESEND_API_URL = "https://api.resend.com/emails"


def encrypt_secret(raw: str | None) -> str | None:
    if raw is None or raw == "":
        return None
    payload = f"{settings.jwt_secret}:{raw}".encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decrypt_secret(raw: str | None) -> str | None:
    if raw is None or raw == "":
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
    except Exception:
        return None
    prefix = f"{settings.jwt_secret}:"
    if not decoded.startswith(prefix):
        return None
    return decoded[len(prefix) :]


def send_tenant_email(
    config: TenantEmailConfig,
    *,
    to_email: str,
    subject: str,
    text_body: str,
) -> None:
    provider = config.provider.strip().lower()
    if provider == "smtp":
        _send_via_smtp(config, to_email=to_email, subject=subject, text_body=text_body)
        return
    if provider == "sendgrid":
        _send_via_sendgrid(config, to_email=to_email, subject=subject, text_body=text_body)
        return
    if provider == "resend":
        api_key = decrypt_secret(config.api_key_encrypted)
        if not api_key:
            raise ValueError("resend_api_key_missing")
        _resend_send(
            api_key=api_key,
            from_address=_from_header(config),
            to_email=to_email,
            subject=subject,
            html=f"<pre>{text_body}</pre>",
        )
        return
    raise ValueError("unsupported_email_provider")


# ---------------------------------------------------------------------------
# Resend provider helpers
# ---------------------------------------------------------------------------

def _resend_send(api_key: str, from_address: str, to_email: str, subject: str, html: str) -> bool:
    """POST one email to the Resend API. Returns True on HTTP 200/201."""
    try:
        resp = httpx.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": from_address, "to": [to_email], "subject": subject, "html": html},
            timeout=10.0,
        )
        if resp.status_code in (200, 201):
            return True
        logger.warning("Resend API %d: %s", resp.status_code, resp.text[:200])
        return False
    except Exception:
        logger.warning("Email send to %s failed", to_email, exc_info=True)
        return False


def _render_template(template_name: str, ctx: dict[str, Any]) -> str:
    return _jinja_env.get_template(template_name).render(**ctx)


def send_order_confirmation(db: Session, order: Order) -> bool:
    """Send order confirmation email to the customer.

    Works with any configured provider (smtp, resend, sendgrid).
    Silently skips when no config exists or config is incomplete.
    Never raises — a failed send must not break order creation.
    """
    if not order.customer_email:
        return False

    config = db.execute(
        select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == order.tenant_id)
    ).scalar_one_or_none()
    if config is None or not config.from_email:
        logger.debug("No email config for tenant %s, skipping order confirmation", order.tenant_id)
        return False

    provider = (config.provider or "").strip().lower()

    # Validate provider has credentials
    if provider == "smtp":
        if not config.smtp_host or not config.smtp_port:
            logger.debug("SMTP config incomplete for tenant %s", order.tenant_id)
            return False
    elif provider in ("resend", "sendgrid"):
        if not decrypt_secret(config.api_key_encrypted):
            logger.debug("%s api key missing for tenant %s", provider, order.tenant_id)
            return False
    else:
        logger.debug("Unknown email provider %r for tenant %s", provider, order.tenant_id)
        return False

    from_name = config.from_name or ""
    lines = db.execute(select(OrderLine).where(OrderLine.order_id == order.id)).scalars().all()

    try:
        html = _render_template("order_confirmation.html", {
            "order_id": str(order.id),
            "customer_email": order.customer_email,
            "customer_name": None,
            "order_lines": lines,
            "currency": order.currency_code,
            "discount_cents": order.discount_cents,
            "shipping_cents": order.shipping_cents,
            "tax_cents": order.tax_cents,
            "total_cents": order.total_cents,
            "shipping_address": order.shipping_address,
            "store_name": from_name,
        })
    except Exception:
        logger.warning("Failed to render order confirmation template", exc_info=True)
        return False

    subject = f"Order Confirmed — #{str(order.id)[:8].upper()}"
    text_fallback = f"Your order has been confirmed. Order ID: {str(order.id)[:8].upper()}"

    try:
        if provider == "smtp":
            _send_via_smtp(config, to_email=order.customer_email, subject=subject,
                           text_body=text_fallback, html_body=html)
            return True
        if provider == "resend":
            api_key = decrypt_secret(config.api_key_encrypted)
            return _resend_send(
                api_key=api_key,
                from_address=_from_header(config),
                to_email=order.customer_email,
                subject=subject,
                html=html,
            )
        if provider == "sendgrid":
            send_tenant_email(config, to_email=order.customer_email,
                              subject=subject, text_body=text_fallback)
            return True
    except Exception:
        logger.warning("Failed to send order confirmation to %s", order.customer_email, exc_info=True)
        return False

    return False


def send_test_email(config: TenantEmailConfig, to_email: str) -> bool:
    """Send a test email using the tenant's configured provider."""
    subject = "IMS Email Configuration Test"
    text = "This is a test email from your IMS store. Your email configuration is working."
    html = f"<p>{text}</p>"
    provider = (config.provider or "").strip().lower()

    try:
        if provider == "smtp":
            _send_via_smtp(config, to_email=to_email, subject=subject,
                           text_body=text, html_body=html)
            return True
        if provider == "resend":
            api_key = decrypt_secret(config.api_key_encrypted)
            if not api_key:
                return False
            return _resend_send(
                api_key=api_key,
                from_address=_from_header(config),
                to_email=to_email,
                subject=subject,
                html=html,
            )
        if provider == "sendgrid":
            send_tenant_email(config, to_email=to_email, subject=subject, text_body=text)
            return True
    except Exception:
        logger.warning("Test email to %s failed", to_email, exc_info=True)
        return False

    return False


def send_abandoned_cart_email(
    db: Session,
    tenant_id: UUID,
    channel_id: UUID,
    cart_token: str,
    customer_email: str,
    checkout_url: str | None = None,
) -> bool:
    """Send an abandoned cart recovery email. Never raises."""
    config = db.execute(
        select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if config is None:
        logger.debug("No email config for tenant %s, skipping abandoned cart email", tenant_id)
        return False

    api_key = decrypt_secret(config.api_key_encrypted)
    provider = (config.provider or "").strip().lower()
    if provider == "resend" and not api_key:
        return False
    if not config.from_email:
        return False

    from app.models import CartItem, Product
    from sqlalchemy import select as sa_select

    rows = db.execute(
        sa_select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.cart_token == cart_token, CartItem.channel_id == channel_id)
    ).all()

    if not rows:
        return False

    cart_items = [
        {
            "product_name": prod.name,
            "quantity": ci.quantity,
            "line_total_cents": ci.unit_price_cents * ci.quantity,
        }
        for ci, prod in rows
    ]
    total_cents = sum(item["line_total_cents"] for item in cart_items)
    first_ci = rows[0][0]
    currency = first_ci.currency_code

    from_name = config.from_name or ""
    from_address = f"{from_name} <{config.from_email}>" if from_name else config.from_email

    try:
        html = _render_template("abandoned_cart.html", {
            "customer_email": customer_email,
            "cart_items": cart_items,
            "currency": currency,
            "total_cents": total_cents,
            "checkout_url": checkout_url,
            "store_name": from_name,
        })
    except Exception:
        logger.warning("Failed to render abandoned_cart template", exc_info=True)
        return False

    subject = "You left something in your cart"

    try:
        if provider == "smtp":
            _send_via_smtp(config, to_email=customer_email, subject=subject,
                           text_body="Complete your order.", html_body=html)
            return True
        if provider == "resend" and api_key:
            return _resend_send(
                api_key=api_key,
                from_address=from_address,
                to_email=customer_email,
                subject=subject,
                html=html,
            )
    except Exception:
        logger.warning("Failed to send abandoned cart email to %s", customer_email, exc_info=True)
    return False


def _send_via_smtp(
    config: TenantEmailConfig,
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> None:
    if not config.smtp_host or not config.smtp_port:
        raise ValueError("smtp_config_incomplete")
    msg = EmailMessage()
    msg["From"] = _from_header(config)
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    password = decrypt_secret(config.smtp_password_encrypted)
    port = int(config.smtp_port)
    if port == 465:
        with smtplib.SMTP_SSL(config.smtp_host, port, timeout=15) as server:
            if config.smtp_username and password:
                server.login(config.smtp_username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(config.smtp_host, port, timeout=15) as server:
            server.starttls()
            if config.smtp_username and password:
                server.login(config.smtp_username, password)
            server.send_message(msg)


def _send_via_sendgrid(
    config: TenantEmailConfig,
    *,
    to_email: str,
    subject: str,
    text_body: str,
) -> None:
    api_key = decrypt_secret(config.api_key_encrypted)
    if not api_key:
        raise ValueError("sendgrid_api_key_missing")
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": config.from_email, "name": config.from_name or config.from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": text_body}],
    }
    req = request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=15) as resp:
        code = resp.getcode()
        if code not in (200, 202):
            raise ValueError("sendgrid_delivery_failed")


def _from_header(config: TenantEmailConfig) -> str:
    if config.from_name:
        return f"{config.from_name} <{config.from_email}>"
    return config.from_email
