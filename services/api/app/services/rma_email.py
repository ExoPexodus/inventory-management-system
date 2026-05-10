"""RMA email delivery helper.

Called by rma_service.py for status-change emails.
Never raises — email failures are non-blocking.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TenantEmailConfig
from app.services.email_service import _render_template, _resend_send, _send_via_smtp, _from_header, decrypt_secret, send_tenant_email

logger = logging.getLogger(__name__)

_SUBJECT_MAP = {
    "rma_received.html": "We received your refund request",
    "rma_approved.html": "Your refund has been approved",
    "rma_rejected.html": "Your refund request was declined",
    "rma_refunded.html": "Your refund has been processed",
}


def send_rma_email(db: Session, *, request, template_name: str) -> bool:
    """Send an RMA status email to the customer.

    Non-blocking — silently returns False on any error.
    """
    to_email = request.customer_email
    if not to_email:
        logger.debug("RMA request %s has no customer_email — skipping email", request.id)
        return False

    config = db.execute(
        select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == request.tenant_id)
    ).scalar_one_or_none()
    if config is None or not config.from_email:
        logger.debug("No email config for tenant %s — skipping RMA email", request.tenant_id)
        return False

    provider = (config.provider or "").strip().lower()
    if provider == "smtp":
        if not config.smtp_host or not config.smtp_port:
            return False
    elif provider in ("resend", "sendgrid"):
        if not decrypt_secret(config.api_key_encrypted):
            return False
    else:
        return False

    rma_id_short = str(request.id)[:8].upper()
    subject = _SUBJECT_MAP.get(template_name, "Update on your refund request") + f" — #{rma_id_short}"

    try:
        html = _render_template(template_name, {
            "rma_id": str(request.id),
            "rma_id_short": rma_id_short,
            "customer_name": request.customer_name or request.customer_email,
            "customer_email": request.customer_email,
            "status": request.status,
            "refund_type": request.refund_type,
            "reason_code": request.reason_code,
            "reason_note": request.reason_note,
            "total_refund_cents": request.total_refund_cents,
            "currency_code": request.currency_code,
            "rejected_reason": request.rejected_reason,
            "lines": request.lines,
            "store_name": config.from_name or "",
        })
    except Exception:
        logger.warning("Failed to render RMA email template %s", template_name, exc_info=True)
        return False

    text_fallback = f"Update on your refund request #{rma_id_short}"

    try:
        if provider == "smtp":
            _send_via_smtp(config, to_email=to_email, subject=subject,
                           text_body=text_fallback, html_body=html)
            return True
        if provider == "resend":
            api_key = decrypt_secret(config.api_key_encrypted)
            return _resend_send(
                api_key=api_key,
                from_address=_from_header(config),
                to_email=to_email,
                subject=subject,
                html=html,
            )
        if provider == "sendgrid":
            send_tenant_email(config, to_email=to_email, subject=subject, text_body=text_fallback)
            return True
    except Exception:
        logger.warning("Failed to send RMA email to %s", to_email, exc_info=True)

    return False
