"""Unified customer resolver: match by email > phone > create new, with channel attribution."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer, CustomerChannel


def resolve_or_create_customer(
    db: Session,
    tenant_id: UUID,
    channel_id: UUID,
    *,
    email: str | None = None,
    phone: str | None = None,
    name: str | None = None,
) -> Customer | None:
    """Resolve or create a customer for an incoming order.

    Match order: email (case-insensitive) > phone > create new.
    Returns None if neither email nor phone is provided.
    Records a customer_channels row on every successful resolve.
    """
    email_norm = email.strip().lower() if email else None
    phone_norm = phone.strip() if phone else None

    if not email_norm and not phone_norm:
        return None

    customer: Customer | None = None

    if email_norm:
        customer = db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                func.lower(Customer.email) == email_norm,
            )
        ).scalar_one_or_none()

    if customer is None and phone_norm:
        customer = db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.phone == phone_norm,
            )
        ).scalar_one_or_none()

    if customer is None:
        # Customer.phone is NOT NULL (VARCHAR 20). When only email is known, use a
        # deterministic placeholder derived from a short hash of the email so it fits
        # within 20 chars and remains recoverable. The customer-cleanup sub-project
        # can later make phone nullable if desired.
        placeholder_phone = f"e:{hashlib.md5(email_norm.encode()).hexdigest()[:12]}" if email_norm else None
        customer = Customer(
            tenant_id=tenant_id,
            phone=phone_norm or placeholder_phone,
            email=email_norm,
            name=name,
            created_via_channel_id=channel_id,
        )
        db.add(customer)
        db.flush()

    _record_channel_attribution(db, tenant_id, customer.id, channel_id)
    return customer


def _record_channel_attribution(
    db: Session, tenant_id: UUID, customer_id: UUID, channel_id: UUID,
) -> None:
    """Upsert a customer_channels row, bumping last_seen_at."""
    existing = db.execute(
        select(CustomerChannel).where(
            CustomerChannel.customer_id == customer_id,
            CustomerChannel.channel_id == channel_id,
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if existing is not None:
        existing.last_seen_at = now
    else:
        db.add(CustomerChannel(
            tenant_id=tenant_id,
            customer_id=customer_id,
            channel_id=channel_id,
            first_seen_at=now,
            last_seen_at=now,
        ))
    db.flush()
