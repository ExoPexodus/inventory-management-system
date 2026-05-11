"""Transfer order state machine and business logic.

State transitions:
  draft ──submit──> pending_approval ──approve──> approved ──ship──> in_transit ──receive──> completed
          │                  │
          │                  └──reject──> rejected
          └──submit (auto-approved)──> approved
  draft | pending_approval | approved ──cancel──> cancelled
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product, Shop, StockMovement, Tenant, TransferOrder, TransferOrderLine

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _snapshot_costs(db: Session, transfer: TransferOrder) -> None:
    """Set unit_cost_at_transfer_cents from Product.cost_price_cents on each line."""
    for line in transfer.lines:
        prod = db.get(Product, line.product_id)
        line.unit_cost_at_transfer_cents = (prod.cost_price_cents or 0) if prod else 0


def _validate_shops(db: Session, tenant_id: UUID, from_shop_id: UUID, to_shop_id: UUID) -> None:
    if from_shop_id == to_shop_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="from_shop_id and to_shop_id must be different",
        )
    from_shop = db.get(Shop, from_shop_id)
    to_shop = db.get(Shop, to_shop_id)
    if from_shop is None or from_shop.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="from_shop not found in this tenant")
    if to_shop is None or to_shop.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="to_shop not found in this tenant")


def _validate_products(db: Session, tenant_id: UUID, product_ids: list[UUID]) -> None:
    if not product_ids:
        return
    rows = db.execute(
        select(Product.id).where(Product.id.in_(product_ids), Product.tenant_id == tenant_id)
    ).scalars().all()
    found = set(rows)
    missing = set(product_ids) - found
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Products not found in tenant: {sorted(str(p) for p in missing)}",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_transfer(
    db: Session,
    *,
    tenant_id: UUID,
    from_shop_id: UUID,
    to_shop_id: UUID,
    created_by_user_id: UUID | None,
    lines: list[dict],  # [{"product_id": UUID, "quantity_requested": int, "line_notes": str|None}]
    notes: str | None = None,
) -> TransferOrder:
    """Create a new draft transfer order."""
    if not lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Transfer must have at least one line",
        )
    _validate_shops(db, tenant_id, from_shop_id, to_shop_id)
    product_ids = [line["product_id"] for line in lines]
    _validate_products(db, tenant_id, product_ids)

    for line in lines:
        if line.get("quantity_requested", 0) <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="All line quantities must be greater than zero",
            )

    transfer = TransferOrder(
        tenant_id=tenant_id,
        from_shop_id=from_shop_id,
        to_shop_id=to_shop_id,
        status="draft",
        created_by_user_id=created_by_user_id,
        notes=notes,
    )
    db.add(transfer)
    db.flush()

    for line in lines:
        db.add(TransferOrderLine(
            transfer_order_id=transfer.id,
            product_id=line["product_id"],
            quantity_requested=line["quantity_requested"],
            line_notes=line.get("line_notes"),
        ))

    db.flush()
    db.refresh(transfer)
    return transfer


def update_draft(
    db: Session,
    *,
    transfer: TransferOrder,
    lines: list[dict],
    notes: str | None = None,
) -> TransferOrder:
    """Update lines and notes on a draft transfer. Only allowed in 'draft' status."""
    if transfer.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft transfers can be edited",
        )
    if not lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Transfer must have at least one line",
        )

    product_ids = [line["product_id"] for line in lines]
    _validate_products(db, transfer.tenant_id, product_ids)

    for line in lines:
        if line.get("quantity_requested", 0) <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="All line quantities must be greater than zero",
            )

    # Replace all lines
    for existing_line in list(transfer.lines):
        db.delete(existing_line)
    db.flush()

    for line in lines:
        db.add(TransferOrderLine(
            transfer_order_id=transfer.id,
            product_id=line["product_id"],
            quantity_requested=line["quantity_requested"],
            line_notes=line.get("line_notes"),
        ))

    transfer.notes = notes
    db.flush()
    db.refresh(transfer)
    return transfer


def submit_transfer(
    db: Session,
    *,
    transfer: TransferOrder,
    tenant: Tenant,
) -> TransferOrder:
    """Transition draft -> pending_approval (or directly to approved via auto-approve)."""
    if transfer.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft transfers can be submitted",
        )
    if not transfer.lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Transfer must have at least one line before submitting",
        )

    # Check auto-approve threshold
    auto_threshold = tenant.transfer_auto_approve_under_cents
    if auto_threshold is not None:
        total = sum(
            line.quantity_requested * (db.get(Product, line.product_id).cost_price_cents or 0)
            for line in transfer.lines
            if db.get(Product, line.product_id) is not None
        )
        if total < auto_threshold:
            # Auto-approve path
            transfer.status = "approved"
            transfer.approved_at = _now()
            transfer.approved_by_user_id = None  # NULL indicates auto-approved
            _snapshot_costs(db, transfer)
            db.flush()
            db.refresh(transfer)
            return transfer

    transfer.status = "pending_approval"
    db.flush()
    db.refresh(transfer)
    return transfer


def approve_transfer(
    db: Session,
    *,
    transfer: TransferOrder,
    tenant: Tenant,
    approving_user_id: UUID,
) -> TransferOrder:
    """Transition pending_approval -> approved. Snapshots costs."""
    if transfer.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending_approval transfers can be approved",
        )

    # Self-approval guard
    if (
        not tenant.transfer_allow_self_approval
        and transfer.created_by_user_id is not None
        and approving_user_id == transfer.created_by_user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Creator cannot approve their own transfer (transfer_allow_self_approval is false)",
        )

    transfer.status = "approved"
    transfer.approved_by_user_id = approving_user_id
    transfer.approved_at = _now()
    _snapshot_costs(db, transfer)
    db.flush()
    db.refresh(transfer)
    return transfer


def reject_transfer(
    db: Session,
    *,
    transfer: TransferOrder,
    rejecting_user_id: UUID,
    reason: str,
) -> TransferOrder:
    """Transition pending_approval -> rejected."""
    if transfer.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending_approval transfers can be rejected",
        )

    transfer.status = "rejected"
    transfer.rejected_at = _now()
    transfer.rejection_reason = reason
    db.flush()
    db.refresh(transfer)
    return transfer


def ship_transfer(
    db: Session,
    *,
    transfer: TransferOrder,
    ship_quantities: dict[UUID, int],  # line_id -> quantity_shipped
) -> TransferOrder:
    """Transition approved -> in_transit. Updates quantity_shipped per line."""
    if transfer.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only approved transfers can be shipped",
        )

    lines_by_id = {line.id: line for line in transfer.lines}
    for line_id, qty in ship_quantities.items():
        line = lines_by_id.get(line_id)
        if line is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Line {line_id} not found in this transfer",
            )
        if qty > line.quantity_requested:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"quantity_shipped ({qty}) exceeds quantity_requested ({line.quantity_requested}) for line {line_id}",
            )
        line.quantity_shipped = qty

    transfer.status = "in_transit"
    transfer.shipped_at = _now()
    db.flush()
    db.refresh(transfer)
    return transfer


def receive_transfer(
    db: Session,
    *,
    transfer: TransferOrder,
    receive_quantities: dict[UUID, int],  # line_id -> quantity_received
) -> TransferOrder:
    """Transition in_transit -> completed. Creates StockMovement records."""
    if transfer.status != "in_transit":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only in_transit transfers can be received",
        )

    lines_by_id = {line.id: line for line in transfer.lines}
    for line_id, qty in receive_quantities.items():
        line = lines_by_id.get(line_id)
        if line is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Line {line_id} not found in this transfer",
            )
        if qty > line.quantity_shipped:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"quantity_received ({qty}) exceeds quantity_shipped ({line.quantity_shipped}) for line {line_id}",
            )
        line.quantity_received = qty

    # Create stock movements for lines with received qty > 0
    for line in transfer.lines:
        qty = receive_quantities.get(line.id, 0)
        if qty <= 0:
            continue

        product = db.get(Product, line.product_id)
        if product is None:
            continue

        # Deduct from source shop
        db.add(StockMovement(
            tenant_id=transfer.tenant_id,
            shop_id=transfer.from_shop_id,
            product_id=line.product_id,
            quantity_delta=-qty,
            movement_type="transfer_out",
            idempotency_key=f"transfer:{transfer.id}:{line.id}:out",
        ))

        # Add to destination shop
        db.add(StockMovement(
            tenant_id=transfer.tenant_id,
            shop_id=transfer.to_shop_id,
            product_id=line.product_id,
            quantity_delta=qty,
            movement_type="transfer_in",
            idempotency_key=f"transfer:{transfer.id}:{line.id}:in",
        ))

    now = _now()
    transfer.status = "completed"
    transfer.received_at = now
    transfer.completed_at = now
    db.flush()
    db.refresh(transfer)
    return transfer


def cancel_transfer(
    db: Session,
    *,
    transfer: TransferOrder,
) -> TransferOrder:
    """Cancel a transfer. Allowed in draft, pending_approval, or approved states."""
    allowed_statuses = {"draft", "pending_approval", "approved"}
    if transfer.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transfers in '{transfer.status}' status cannot be cancelled",
        )

    transfer.status = "cancelled"
    transfer.cancelled_at = _now()
    db.flush()
    db.refresh(transfer)
    return transfer


def get_committed_to_transfers(db: Session, *, shop_id: UUID, product_id: UUID) -> int:
    """Return sum of (quantity_requested - quantity_shipped) across lines
    in approved/in_transit transfers from the given shop for the given product.
    """
    rows = db.execute(
        select(TransferOrderLine).join(
            TransferOrder,
            TransferOrderLine.transfer_order_id == TransferOrder.id,
        ).where(
            TransferOrder.from_shop_id == shop_id,
            TransferOrderLine.product_id == product_id,
            TransferOrder.status.in_(["approved", "in_transit"]),
        )
    ).scalars().all()

    return sum(max(0, line.quantity_requested - line.quantity_shipped) for line in rows)


def get_committed_to_transfers_batch(
    db: Session, *, shop_id: UUID, product_ids: list[UUID],
) -> dict[UUID, int]:
    """Batch version of get_committed_to_transfers. Returns {product_id: committed_qty}
    for every id in product_ids (default 0 when no pending lines)."""
    if not product_ids:
        return {}
    from sqlalchemy import func as _func  # noqa: PLC0415

    rows = db.execute(
        select(
            TransferOrderLine.product_id,
            _func.coalesce(_func.sum(TransferOrderLine.quantity_requested - TransferOrderLine.quantity_shipped), 0),
        )
        .join(TransferOrder, TransferOrderLine.transfer_order_id == TransferOrder.id)
        .where(
            TransferOrder.from_shop_id == shop_id,
            TransferOrderLine.product_id.in_(product_ids),
            TransferOrder.status.in_(["approved", "in_transit"]),
        )
        .group_by(TransferOrderLine.product_id)
    ).all()
    out: dict[UUID, int] = {pid: 0 for pid in product_ids}
    for pid, qty in rows:
        out[pid] = max(0, int(qty))
    return out
