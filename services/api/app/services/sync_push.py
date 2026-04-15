from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Device,
    Notification,
    PaymentAllocation,
    Product,
    Shop,
    ShopProductTax,
    StockMovement,
    Transaction,
    TransactionLine,
)
from app.db.rls import set_rls_context
from app.services.stock import current_quantity
from app.services.tax import sale_tax_totals


@dataclass
class AppliedResult:
    client_mutation_id: str
    server_transaction_id: UUID | None
    status: str
    detail: str | None = None
    conflict: dict[str, Any] | None = None


def _parse_tender(t: str) -> str:
    t = t.lower().strip()
    if t not in ("cash", "card", "gateway"):
        raise ValueError("invalid_tender")
    return t


def apply_sale_completed(
    db: Session,
    *,
    tenant_id: UUID,
    device_id: UUID,
    allowed_shop_ids: list[UUID],
    event: dict[str, Any],
    assume_online_for_card: bool = True,
) -> AppliedResult:
    # Optional client timestamp (OpenAPI parity); not persisted on Transaction in MVP.
    _occurred_at = event.get("occurred_at")

    client_mutation_id = event["client_mutation_id"]
    shop_id = UUID(str(event["shop_id"]))

    if shop_id not in allowed_shop_ids:
        return AppliedResult(
            client_mutation_id,
            None,
            "rejected",
            "shop_not_allowed_for_device",
            conflict={
                "code": "shop_not_allowed_for_device",
                "shop_id": str(shop_id),
            },
        )

    existing = db.execute(
        select(Transaction).where(
            Transaction.tenant_id == tenant_id,
            Transaction.client_mutation_id == client_mutation_id,
        )
    ).scalar_one_or_none()
    if existing:
        return AppliedResult(
            client_mutation_id,
            existing.id,
            "duplicate",
            None,
        )

    lines_in = event.get("lines") or []
    payments_in = event.get("payments") or []
    if not lines_in:
        return AppliedResult(
            client_mutation_id,
            None,
            "rejected",
            "no_lines",
            conflict={"code": "no_lines"},
        )

    shop_row = db.get(Shop, shop_id)
    if shop_row is None or shop_row.tenant_id != tenant_id:
        return AppliedResult(
            client_mutation_id,
            None,
            "rejected",
            "unknown_shop",
            conflict={"code": "unknown_shop", "shop_id": str(shop_id)},
        )

    parsed_lines: list[tuple[Product, int, int]] = []
    for li in lines_in:
        pid = UUID(str(li["product_id"]))
        qty = int(li["quantity"])
        price = int(li["unit_price_cents"])
        if qty < 1 or price < 0:
            return AppliedResult(
                client_mutation_id,
                None,
                "rejected",
                "bad_line",
                conflict={"code": "bad_line", "product_id": str(pid)},
            )
        prod = db.execute(
            select(Product).where(Product.id == pid, Product.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if prod is None or not prod.active:
            return AppliedResult(
                client_mutation_id,
                None,
                "rejected",
                "unknown_product",
                conflict={"code": "unknown_product", "product_id": str(pid)},
            )
        parsed_lines.append((prod, qty, price))

    pids = [p.id for p, _, _ in parsed_lines]
    override_rows = db.execute(
        select(ShopProductTax).where(
            ShopProductTax.shop_id == shop_id,
            ShopProductTax.product_id.in_(pids),
        )
    ).scalars().all()
    overrides: dict[UUID, ShopProductTax] = {r.product_id: r for r in override_rows}

    subtotal_cents, tax_cents = sale_tax_totals(shop_row, parsed_lines, overrides)
    grand_total = subtotal_cents + tax_cents

    tender_total = 0
    parsed_payments: list[tuple[str, int, str | None, str | None, dict | None]] = []
    for p in payments_in:
        tender = _parse_tender(str(p["tender_type"]))
        if tender == "card" and not assume_online_for_card:
            return AppliedResult(
                client_mutation_id,
                None,
                "rejected",
                "card_requires_connectivity",
                conflict={"code": "card_requires_connectivity"},
            )
        amt = int(p["amount_cents"])
        if amt < 0:
            return AppliedResult(
                client_mutation_id,
                None,
                "rejected",
                "bad_payment",
                conflict={"code": "bad_payment"},
            )
        tender_total += amt
        parsed_payments.append(
            (
                tender,
                amt,
                p.get("gateway_provider"),
                p.get("external_ref"),
                p.get("metadata"),
            )
        )

    if tender_total != grand_total:
        return AppliedResult(
            client_mutation_id,
            None,
            "rejected",
            "payment_total_mismatch",
            conflict={
                "code": "payment_total_mismatch",
                "subtotal_cents": subtotal_cents,
                "tax_cents": tax_cents,
                "grand_total_cents": grand_total,
                "tender_total_cents": tender_total,
            },
        )

    for prod, qty, _ in parsed_lines:
        pid = prod.id
        avail = current_quantity(db, shop_id, pid)
        if avail < qty:
            prod_row = db.execute(
                select(Product).where(Product.id == pid, Product.tenant_id == tenant_id)
            ).scalar_one_or_none()
            return AppliedResult(
                client_mutation_id,
                None,
                "rejected",
                "insufficient_stock",
                conflict={
                    "code": "insufficient_stock",
                    "product_id": str(pid),
                    "sku": prod_row.sku if prod_row else None,
                    "name": prod_row.name if prod_row else None,
                    "available_quantity": avail,
                    "requested_quantity": qty,
                },
            )

    device_row = db.get(Device, device_id) if device_id else None
    employee_id = device_row.employee_id if device_row else None

    txn = Transaction(
        tenant_id=tenant_id,
        shop_id=shop_id,
        device_id=device_id,
        employee_id=employee_id,
        total_cents=grand_total,
        tax_cents=tax_cents,
        client_mutation_id=client_mutation_id,
    )
    db.add(txn)
    db.flush()

    for prod, qty, price in parsed_lines:
        pid = prod.id
        db.add(
            TransactionLine(
                transaction_id=txn.id,
                product_id=pid,
                quantity=qty,
                unit_price_cents=price,
            )
        )
        db.add(
            StockMovement(
                tenant_id=tenant_id,
                shop_id=shop_id,
                product_id=pid,
                quantity_delta=-qty,
                movement_type="sale_out",
                transaction_id=txn.id,
                idempotency_key=f"{client_mutation_id}:{pid}",
            )
        )

    for tender, amt, gprov, extref, meta in parsed_payments:
        db.add(
            PaymentAllocation(
                transaction_id=txn.id,
                tender_type=tender,
                amount_cents=amt,
                gateway_provider=gprov,
                external_ref=extref,
                extra=meta,
            )
        )

    _ = _occurred_at  # reserved for future auditing / conflict checks
    db.flush()
    db.refresh(txn)

    # Fire stock-low notifications for any product that crossed its reorder_point
    for prod, qty, _ in parsed_lines:
        if prod.reorder_point and prod.reorder_point > 0:
            new_qty = current_quantity(db, shop_id, prod.id)
            if new_qty <= prod.reorder_point:
                db.add(
                    Notification(
                        tenant_id=tenant_id,
                        type="stock_low",
                        title=f"Low stock: {prod.name}",
                        body=f"On-hand quantity is {new_qty} (reorder point: {prod.reorder_point})",
                        resource_type="product",
                        resource_id=str(prod.id),
                    )
                )
    db.flush()

    return AppliedResult(client_mutation_id, txn.id, "accepted", None, None)


def apply_ledger_adjustment(
    db: Session,
    *,
    tenant_id: UUID,
    allowed_shop_ids: list[UUID],
    event: dict[str, Any],
) -> AppliedResult:
    client_mutation_id = event["client_mutation_id"]
    shop_id = UUID(str(event["shop_id"]))
    product_id = UUID(str(event["product_id"]))
    qty_delta = int(event["quantity_delta"])
    reason_raw = str(event.get("reason") or "adjustment")
    movement_type = reason_raw[:32]

    if shop_id not in allowed_shop_ids:
        return AppliedResult(
            client_mutation_id,
            None,
            "rejected",
            "shop_not_allowed_for_device",
            conflict={"code": "shop_not_allowed_for_device", "shop_id": str(shop_id)},
        )

    if qty_delta == 0:
        return AppliedResult(
            client_mutation_id,
            None,
            "rejected",
            "zero_delta",
            conflict={"code": "zero_delta"},
        )

    existing = db.execute(
        select(StockMovement).where(
            StockMovement.tenant_id == tenant_id,
            StockMovement.shop_id == shop_id,
            StockMovement.product_id == product_id,
            StockMovement.idempotency_key == client_mutation_id,
        )
    ).scalar_one_or_none()
    if existing:
        return AppliedResult(client_mutation_id, None, "duplicate", None, None)

    prod = db.execute(
        select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if prod is None or not prod.active:
        return AppliedResult(
            client_mutation_id,
            None,
            "rejected",
            "unknown_product",
            conflict={"code": "unknown_product", "product_id": str(product_id)},
        )

    avail = current_quantity(db, shop_id, product_id)
    if qty_delta < 0 and avail + qty_delta < 0:
        return AppliedResult(
            client_mutation_id,
            None,
            "rejected",
            "insufficient_stock",
            conflict={
                "code": "insufficient_stock",
                "product_id": str(product_id),
                "sku": prod.sku,
                "name": prod.name,
                "available_quantity": avail,
                "requested_delta": qty_delta,
            },
        )

    db.add(
        StockMovement(
            tenant_id=tenant_id,
            shop_id=shop_id,
            product_id=product_id,
            quantity_delta=qty_delta,
            movement_type=movement_type,
            transaction_id=None,
            idempotency_key=client_mutation_id,
        )
    )
    db.flush()
    return AppliedResult(client_mutation_id, None, "accepted", None, None)


def process_push_batch(
    db: Session,
    *,
    tenant_id: UUID,
    device_id: UUID,
    allowed_shop_ids: list[UUID],
    idempotency_key: str,
    events: list[dict[str, Any]],
) -> tuple[list[AppliedResult], str]:
    results: list[AppliedResult] = []
    for ev in events:
        set_rls_context(db, is_admin=False, tenant_id=tenant_id)
        typ = ev.get("type")
        if typ == "sale_completed":
            r = apply_sale_completed(
                db,
                tenant_id=tenant_id,
                device_id=device_id,
                allowed_shop_ids=allowed_shop_ids,
                event=ev,
                assume_online_for_card=True,
            )
            results.append(r)
        elif typ == "ledger_adjustment":
            r = apply_ledger_adjustment(
                db,
                tenant_id=tenant_id,
                allowed_shop_ids=allowed_shop_ids,
                event=ev,
            )
            results.append(r)
        else:
            results.append(
                AppliedResult(
                    ev.get("client_mutation_id", ""),
                    None,
                    "rejected",
                    f"unknown_event:{typ}",
                    conflict={"code": "unknown_event", "event_type": typ},
                )
            )
    new_cursor = datetime.now(UTC).isoformat()
    return results, new_cursor
