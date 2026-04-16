"""Invoice management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import OperatorDep
from app.db.session import get_db
from app.models.tables import Invoice
from app.services.audit_service import write_audit

router = APIRouter(prefix="/v1/platform", tags=["Platform Invoices"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InvoiceOut(BaseModel):
    id: UUID
    tenant_id: UUID
    subscription_id: UUID | None
    payment_id: UUID | None
    invoice_number: str
    status: str
    seller_gstin: str | None
    buyer_gstin: str | None
    seller_legal_name: str | None
    buyer_legal_name: str | None
    place_of_supply: str | None
    line_items: list[dict]
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    currency_code: str
    issued_at: datetime | None
    due_at: datetime | None
    file_url: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# List invoices
# ---------------------------------------------------------------------------


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
    inv_status: str | None = Query(default=None, alias="status"),
    tenant_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[InvoiceOut]:
    stmt = select(Invoice).order_by(Invoice.created_at.desc())
    if inv_status:
        stmt = stmt.where(Invoice.status == inv_status)
    if tenant_id:
        stmt = stmt.where(Invoice.tenant_id == tenant_id)
    stmt = stmt.limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [_to_out(inv) for inv in rows]


@router.get("/tenants/{tenant_id}/invoices", response_model=list[InvoiceOut])
def list_tenant_invoices(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
) -> list[InvoiceOut]:
    rows = db.execute(
        select(Invoice)
        .where(Invoice.tenant_id == tenant_id)
        .order_by(Invoice.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [_to_out(inv) for inv in rows]


# ---------------------------------------------------------------------------
# Get single invoice
# ---------------------------------------------------------------------------


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> InvoiceOut:
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return _to_out(inv)


# ---------------------------------------------------------------------------
# Void invoice
# ---------------------------------------------------------------------------


@router.post("/invoices/{invoice_id}/void", response_model=InvoiceOut)
def void_invoice(
    invoice_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> InvoiceOut:
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    if inv.status == "void":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice is already voided")

    inv.status = "void"
    write_audit(db, operator_id=ctx.operator_id, action="void_invoice", resource_type="invoice", resource_id=str(invoice_id))
    db.commit()
    db.refresh(inv)
    return _to_out(inv)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_out(inv: Invoice) -> InvoiceOut:
    return InvoiceOut(
        id=inv.id,
        tenant_id=inv.tenant_id,
        subscription_id=inv.subscription_id,
        payment_id=inv.payment_id,
        invoice_number=inv.invoice_number,
        status=inv.status,
        seller_gstin=inv.seller_gstin,
        buyer_gstin=inv.buyer_gstin,
        seller_legal_name=inv.seller_legal_name,
        buyer_legal_name=inv.buyer_legal_name,
        place_of_supply=inv.place_of_supply,
        line_items=inv.line_items,
        subtotal_cents=inv.subtotal_cents,
        tax_cents=inv.tax_cents,
        total_cents=inv.total_cents,
        currency_code=inv.currency_code,
        issued_at=inv.issued_at,
        due_at=inv.due_at,
        file_url=inv.file_url,
        created_at=inv.created_at,
    )
