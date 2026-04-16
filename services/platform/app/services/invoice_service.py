"""Invoice generation service.

Creates invoices from payments with GST support for Indian B2B transactions.
Invoice numbers are sequential per year: INV-YYYY-NNNN.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.tables import (
    Addon,
    Invoice,
    Payment,
    Plan,
    PlatformTenant,
    Subscription,
    SubscriptionAddon,
)


def generate_invoice_for_payment(
    db: Session,
    payment: Payment,
    *,
    seller_gstin: str | None = None,
    seller_legal_name: str | None = None,
    buyer_gstin: str | None = None,
    buyer_legal_name: str | None = None,
    place_of_supply: str | None = None,
    tax_rate_pct: float = 18.0,  # default GST rate
) -> Invoice:
    """Generate an invoice for a completed payment."""
    tenant = db.get(PlatformTenant, payment.tenant_id)
    sub = db.get(Subscription, payment.subscription_id)
    plan = db.get(Plan, sub.plan_id) if sub else None

    # Build line items
    line_items = []

    if plan:
        base_price = plan.base_price_cents
        if sub and sub.billing_cycle == "yearly":
            base_price = int(base_price * 12 * (1 - plan.yearly_discount_pct / 100))
            period_label = "Yearly"
        else:
            period_label = "Monthly"

        line_items.append({
            "description": f"{plan.display_name} Plan - {period_label} Subscription",
            "hsn_code": "998314",  # SAC code for IT services
            "qty": 1,
            "unit_price_cents": base_price,
            "tax_rate_pct": tax_rate_pct,
            "tax_cents": int(base_price * tax_rate_pct / 100),
            "total_cents": base_price + int(base_price * tax_rate_pct / 100),
        })

    # Add-on line items
    if sub:
        addon_rows = db.execute(
            select(SubscriptionAddon, Addon)
            .join(Addon, Addon.id == SubscriptionAddon.addon_id)
            .where(
                SubscriptionAddon.subscription_id == sub.id,
                SubscriptionAddon.removed_at.is_(None),
            )
        ).all()

        for sa, addon in addon_rows:
            addon_price = addon.price_cents
            if sub.billing_cycle == "yearly" and plan:
                addon_price = int(addon_price * 12 * (1 - plan.yearly_discount_pct / 100))

            line_items.append({
                "description": f"{addon.display_name} Add-on",
                "hsn_code": "998314",
                "qty": 1,
                "unit_price_cents": addon_price,
                "tax_rate_pct": tax_rate_pct,
                "tax_cents": int(addon_price * tax_rate_pct / 100),
                "total_cents": addon_price + int(addon_price * tax_rate_pct / 100),
            })

    subtotal = sum(li["unit_price_cents"] for li in line_items)
    tax_total = sum(li["tax_cents"] for li in line_items)
    grand_total = subtotal + tax_total

    invoice_number = _next_invoice_number(db)

    invoice = Invoice(
        id=_uuid.uuid4(),
        tenant_id=payment.tenant_id,
        subscription_id=payment.subscription_id,
        payment_id=payment.id,
        invoice_number=invoice_number,
        status="issued",
        seller_gstin=seller_gstin,
        buyer_gstin=buyer_gstin,
        seller_legal_name=seller_legal_name,
        buyer_legal_name=buyer_legal_name or (tenant.name if tenant else None),
        place_of_supply=place_of_supply,
        line_items=line_items,
        subtotal_cents=subtotal,
        tax_cents=tax_total,
        total_cents=grand_total,
        currency_code=payment.currency_code,
        issued_at=datetime.now(UTC),
        due_at=datetime.now(UTC) + timedelta(days=30),
    )
    db.add(invoice)
    db.flush()
    return invoice


def _next_invoice_number(db: Session) -> str:
    """Generate the next sequential invoice number: INV-YYYY-NNNN."""
    year = datetime.now(UTC).year
    prefix = f"INV-{year}-"

    count = db.execute(
        select(func.count(Invoice.id)).where(Invoice.invoice_number.like(f"{prefix}%"))
    ).scalar_one()

    return f"{prefix}{count + 1:04d}"
