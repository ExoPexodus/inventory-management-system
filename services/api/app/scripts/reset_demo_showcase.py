"""Wipe all tenant-scoped data and load a rich demo dataset. Preserves `admin_users` (operators).

Use for demos / feature showcases. **Destructive**: deletes every tenant and related rows.

Run inside the API container / with DATABASE_URL set:

  IMS_DEMO_RESET_OK=1 python -m app.scripts.reset_demo_showcase

Also prints a fresh enrollment token for cashier device onboarding.
"""

from __future__ import annotations

import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.rls import set_rls_context
from app.db.session import SessionLocal
from app.models import (
    AdminUser,
    EnrollmentToken,
    PaymentAllocation,
    Product,
    ProductGroup,
    PurchaseOrder,
    PurchaseOrderLine,
    Shop,
    ShopProductTax,
    StockAdjustment,
    StockMovement,
    Supplier,
    Tenant,
    TransferOrder,
    TransferOrderLine,
    Transaction,
    TransactionLine,
)
from app.services.enrollment import hash_token
from app.services.tax import sale_tax_totals


FIXED_SLUG = "showcase-demo"


def _require_confirmation() -> None:
    if os.environ.get("IMS_DEMO_RESET_OK", "").strip() != "1":
        raise SystemExit(
            "Refusing to reset: set IMS_DEMO_RESET_OK=1 to confirm you want to delete all tenant data.\n"
            "Example: IMS_DEMO_RESET_OK=1 python -m app.scripts.reset_demo_showcase"
        )


def _wipe_tenants(db: Session) -> None:
    """Remove all tenants (CASCADE removes shops, products, transactions, etc.). Keeps admin_users."""
    set_rls_context(db, is_admin=True, tenant_id=None)
    db.execute(text("DELETE FROM tenants"))
    db.commit()


def _add_opening_stock(
    db: Session,
    tenant_id: UUID,
    shop_id: UUID,
    inventory: dict[UUID, int],
    prefix: str,
) -> None:
    for pid, qty in inventory.items():
        db.add(
            StockMovement(
                tenant_id=tenant_id,
                shop_id=shop_id,
                product_id=pid,
                quantity_delta=qty,
                movement_type="adjustment",
                transaction_id=None,
                idempotency_key=f"{prefix}:open:{pid}",
            )
        )


def _sale_txn(
    db: Session,
    *,
    tenant_id: UUID,
    shop: Shop,
    product_by_sku: dict[str, Product],
    sku_qty: list[tuple[str, int]],
    tender: str,
    when: datetime,
    status: str,
    mutation_suffix: str,
    tax_overrides: dict[UUID, ShopProductTax],
) -> None:
    lines: list[tuple[Product, int, int]] = []
    for sku, qty in sku_qty:
        p = product_by_sku[sku]
        lines.append((p, qty, p.unit_price_cents))

    subtotal_cents, tax_cents = sale_tax_totals(shop, lines, tax_overrides)
    grand_total = subtotal_cents + tax_cents

    txn = Transaction(
        tenant_id=tenant_id,
        shop_id=shop.id,
        device_id=None,
        kind="sale",
        status=status,
        total_cents=grand_total,
        tax_cents=tax_cents,
        client_mutation_id=f"showcase-{mutation_suffix}",
        created_at=when,
    )
    db.add(txn)
    db.flush()

    for prod, qty, price in lines:
        db.add(
            TransactionLine(
                transaction_id=txn.id,
                product_id=prod.id,
                quantity=qty,
                unit_price_cents=price,
            )
        )
        if status == "posted":
            db.add(
                StockMovement(
                    tenant_id=tenant_id,
                    shop_id=shop.id,
                    product_id=prod.id,
                    quantity_delta=-qty,
                    movement_type="sale",
                    transaction_id=txn.id,
                    idempotency_key=f"showcase:sale:{txn.id}:{prod.id}",
                )
            )

    db.add(
        PaymentAllocation(
            transaction_id=txn.id,
            tender_type=tender,
            amount_cents=grand_total,
        )
    )


def main() -> None:
    _require_confirmation()
    raw_enrollment = secrets.token_urlsafe(24)
    db = SessionLocal()
    try:
        _wipe_tenants(db)
        set_rls_context(db, is_admin=True, tenant_id=None)

        tenant = Tenant(
            name="Showcase Market",
            slug=FIXED_SLUG,
            default_currency_code="USD",
            currency_exponent=2,
            currency_symbol_override=None,
            offline_tier="strict",
            max_offline_minutes=60,
        )
        db.add(tenant)
        db.flush()

        shop_downtown = Shop(tenant_id=tenant.id, name="Downtown Store", default_tax_rate_bps=825)
        shop_west = Shop(tenant_id=tenant.id, name="Westside Outlet", default_tax_rate_bps=725)
        db.add_all([shop_downtown, shop_west])
        db.flush()

        grp_bev = ProductGroup(
            tenant_id=tenant.id,
            title="Beverages",
            notes="Demo coffee and drinks",
        )
        grp_apparel = ProductGroup(
            tenant_id=tenant.id,
            title="Apparel",
            notes="Hats and basics",
        )
        db.add_all([grp_bev, grp_apparel])
        db.flush()

        product_specs: list[tuple[str, str, int, str, UUID | None, str | None]] = [
            ("SFT-AMER", "Americano", 350, "Beverages", grp_bev.id, "12 oz"),
            ("SFT-LATTE", "Latte", 495, "Beverages", grp_bev.id, "16 oz"),
            ("SFT-TEA", "Green tea", 275, "Beverages", grp_bev.id, None),
            ("GEN-WATER", "Still water", 200, "Grocery", None, None),
            ("GEN-BAR", "Energy bar", 225, "Grocery", None, None),
            ("APP-HAT-S", "Canvas cap", 1999, "Apparel", grp_apparel.id, "S"),
            ("APP-HAT-M", "Canvas cap", 1999, "Apparel", grp_apparel.id, "M"),
            ("APP-TOTE", "Tote bag", 2495, "Apparel", None, None),
            ("OFF-NOTE", "Desk notepad", 599, "Stationery", None, None),
            ("OFF-PEN", "Gel pen 2pk", 449, "Stationery", None, None),
            ("LOW-STK", "Promo sticker roll", 150, "Stationery", None, None),
        ]

        products: list[Product] = []
        for sku, name, price, category, gid, vlabel in product_specs:
            p = Product(
                tenant_id=tenant.id,
                product_group_id=gid,
                sku=sku,
                name=name,
                category=category,
                status="archived" if sku == "APP-HAT-S" else "active",
                description=f"Showcase item for {category.lower()} merchandising",
                image_url=f"https://picsum.photos/seed/{sku.lower()}/640/640",
                reorder_point=8 if sku in {"LOW-STK", "OFF-PEN"} else 20,
                unit_price_cents=price,
                variant_label=vlabel,
                active=True,
            )
            db.add(p)
            db.flush()
            products.append(p)

        product_by_sku = {p.sku: p for p in products}

        suppliers_data = [
            ("Metro Roasters Co.", "active", "orders@metroroasters.test", "+1-555-0101", "Primary coffee beans"),
            ("Pacific Packaging", "active", "hello@pacificpack.test", "+1-555-0102", None),
            ("QuickShip Logistics", "active", "ops@quickship.test", None, "Outbound freight"),
            ("Old Harbor Wholesale", "inactive", "archive@oldharbor.test", None, "Paused — seasonal only"),
        ]
        suppliers: list[Supplier] = []
        for name, st, em, ph, notes in suppliers_data:
            supplier = Supplier(
                tenant_id=tenant.id,
                name=name,
                status=st,
                contact_email=em,
                contact_phone=ph,
                notes=notes,
            )
            db.add(supplier)
            suppliers.append(supplier)
        db.flush()

        # Downtown: americano tax-exempt for demo overrides
        tax_exempt = ShopProductTax(
            tenant_id=tenant.id,
            shop_id=shop_downtown.id,
            product_id=product_by_sku["SFT-AMER"].id,
            tax_exempt=True,
            effective_tax_rate_bps=None,
        )
        # Westside: custom rate on latte
        tax_custom = ShopProductTax(
            tenant_id=tenant.id,
            shop_id=shop_west.id,
            product_id=product_by_sku["SFT-LATTE"].id,
            tax_exempt=False,
            effective_tax_rate_bps=500,
        )
        db.add_all([tax_exempt, tax_custom])
        db.flush()

        tax_overrides_dd: dict[UUID, ShopProductTax] = {
            tax_exempt.product_id: tax_exempt,
        }
        tax_overrides_west: dict[UUID, ShopProductTax] = {
            tax_custom.product_id: tax_custom,
        }

        # Opening inventory — generous stock; LOW-STK intentionally small for alerts
        downtown_inv = {p.id: 120 for p in products}
        downtown_inv[product_by_sku["LOW-STK"].id] = 4
        west_inv = {p.id: 55 for p in products}
        west_inv[product_by_sku["LOW-STK"].id] = 3

        _add_opening_stock(db, tenant.id, shop_downtown.id, downtown_inv, "showcase-dd")
        _add_opening_stock(db, tenant.id, shop_west.id, west_inv, "showcase-ws")

        now = datetime.now(UTC)
        # Historical sales (posted) — spread for analytics chart
        scenarios: list[tuple[Shop, dict[UUID, ShopProductTax], str, list[tuple[str, int]], str, int, str]] = [
            (shop_downtown, tax_overrides_dd, "posted", [("SFT-LATTE", 2), ("GEN-BAR", 1)], "cash", 1, "a"),
            (shop_downtown, tax_overrides_dd, "posted", [("SFT-AMER", 1), ("OFF-PEN", 1)], "card", 2, "b"),
            (shop_west, tax_overrides_west, "posted", [("SFT-LATTE", 1), ("APP-TOTE", 1)], "cash", 10, "c"),
            (shop_downtown, tax_overrides_dd, "posted", [("APP-HAT-M", 2)], "card", 3, "d"),
            (shop_west, tax_overrides_west, "posted", [("GEN-WATER", 3), ("OFF-NOTE", 1)], "cash", 4, "e"),
            (shop_downtown, tax_overrides_dd, "posted", [("SFT-TEA", 2), ("GEN-BAR", 2)], "cash", 5, "f"),
            (shop_west, tax_overrides_west, "posted", [("APP-HAT-S", 1), ("OFF-PEN", 2)], "card", 6, "g"),
            (shop_downtown, tax_overrides_dd, "posted", [("SFT-LATTE", 3)], "card", 7, "h"),
            (shop_downtown, tax_overrides_dd, "posted", [("APP-TOTE", 1), ("GEN-BAR", 1)], "cash", 8, "i"),
            (shop_west, tax_overrides_west, "posted", [("SFT-AMER", 2)], "cash", 9, "j"),
            (shop_downtown, tax_overrides_dd, "posted", [("OFF-NOTE", 2), ("GEN-WATER", 2)], "card", 11, "k"),
            (shop_west, tax_overrides_west, "posted", [("LOW-STK", 1)], "cash", 12, "l"),
            (shop_downtown, tax_overrides_dd, "posted", [("SFT-LATTE", 1), ("SFT-AMER", 2)], "card", 13, "m"),
            (shop_downtown, tax_overrides_dd, "posted", [("APP-HAT-S", 1), ("APP-HAT-M", 1)], "cash", 14, "n"),
            (shop_west, tax_overrides_west, "posted", [("SFT-TEA", 1), ("OFF-PEN", 3)], "cash", 0, "o"),
            (shop_downtown, tax_overrides_dd, "posted", [("GEN-BAR", 4)], "card", 0, "p"),
        ]

        for shop, tax_ov, st, lines, tender, days_ago, suf in scenarios:
            when = now - timedelta(days=days_ago, hours=3 + len(suf))
            _sale_txn(
                db,
                tenant_id=tenant.id,
                shop=shop,
                product_by_sku=product_by_sku,
                sku_qty=lines,
                tender=tender,
                when=when,
                status=st,
                mutation_suffix=suf,
                tax_overrides=tax_ov,
            )

        # Pending sale (no stock deduction)
        _sale_txn(
            db,
            tenant_id=tenant.id,
            shop=shop_downtown,
            product_by_sku=product_by_sku,
            sku_qty=[("SFT-LATTE", 1), ("GEN-BAR", 2)],
            tender="card",
            when=now - timedelta(hours=2),
            status="pending",
            mutation_suffix="pending-1",
            tax_overrides=tax_overrides_dd,
        )

        # Refunded sale (still show line items; skip stock deduction in _sale_txn by status)
        _sale_txn(
            db,
            tenant_id=tenant.id,
            shop=shop_west,
            product_by_sku=product_by_sku,
            sku_qty=[("APP-TOTE", 1)],
            tender="card",
            when=now - timedelta(days=2, hours=5),
            status="refunded",
            mutation_suffix="refund-1",
            tax_overrides=tax_overrides_west,
        )

        manual_adj = StockMovement(
            tenant_id=tenant.id,
            shop_id=shop_downtown.id,
            product_id=product_by_sku["OFF-NOTE"].id,
            quantity_delta=25,
            movement_type="receipt",
            transaction_id=None,
            idempotency_key="showcase:manual-receipt-1",
            created_at=now - timedelta(days=6),
        )
        db.add(manual_adj)

        spoilage = StockMovement(
            tenant_id=tenant.id,
            shop_id=shop_west.id,
            product_id=product_by_sku["GEN-BAR"].id,
            quantity_delta=-2,
            movement_type="shrink",
            transaction_id=None,
            idempotency_key="showcase:shrink-1",
            created_at=now - timedelta(days=4),
        )
        db.add(spoilage)

        db.add(
            EnrollmentToken(
                tenant_id=tenant.id,
                shop_id=shop_downtown.id,
                token_hash=hash_token(raw_enrollment),
                expires_at=datetime.now(UTC) + timedelta(days=14),
            )
        )

        # Strict admin-web scope: bind all existing operators to the showcase tenant.
        admins = db.execute(select(AdminUser)).scalars().all()
        for admin in admins:
            admin.tenant_id = tenant.id
            admin.is_active = True
            if not admin.display_name:
                admin.display_name = admin.email.split("@", 1)[0].replace(".", " ").title()
            if not admin.avatar_url:
                admin.avatar_url = f"https://api.dicebear.com/9.x/identicon/svg?seed={admin.email}"

        owner_admin_id = admins[0].id if admins else None

        # Procurement + stock control showcase data
        main_supplier = suppliers[0] if suppliers else None
        if main_supplier is not None:
            po_draft = PurchaseOrder(
                tenant_id=tenant.id,
                supplier_id=main_supplier.id,
                status="draft",
                expected_delivery_date=now + timedelta(days=3),
                notes="Weekly replenishment draft",
                created_by=owner_admin_id,
            )
            po_ordered = PurchaseOrder(
                tenant_id=tenant.id,
                supplier_id=main_supplier.id,
                status="ordered",
                expected_delivery_date=now + timedelta(days=1),
                notes="Urgent beverage restock",
                created_by=owner_admin_id,
            )
            po_received = PurchaseOrder(
                tenant_id=tenant.id,
                supplier_id=main_supplier.id,
                status="received",
                expected_delivery_date=now - timedelta(days=1),
                notes="Received and stocked",
                created_by=owner_admin_id,
            )
            db.add_all([po_draft, po_ordered, po_received])
            db.flush()

            db.add_all(
                [
                    PurchaseOrderLine(
                        purchase_order_id=po_draft.id,
                        product_id=product_by_sku["OFF-PEN"].id,
                        quantity_ordered=60,
                        quantity_received=0,
                        unit_cost_cents=180,
                    ),
                    PurchaseOrderLine(
                        purchase_order_id=po_ordered.id,
                        product_id=product_by_sku["SFT-LATTE"].id,
                        quantity_ordered=80,
                        quantity_received=0,
                        unit_cost_cents=270,
                    ),
                    PurchaseOrderLine(
                        purchase_order_id=po_received.id,
                        product_id=product_by_sku["LOW-STK"].id,
                        quantity_ordered=120,
                        quantity_received=120,
                        unit_cost_cents=45,
                    ),
                ]
            )

            db.add(
                StockMovement(
                    tenant_id=tenant.id,
                    shop_id=shop_downtown.id,
                    product_id=product_by_sku["LOW-STK"].id,
                    quantity_delta=120,
                    movement_type="receipt",
                    transaction_id=None,
                    idempotency_key="showcase:po-receive:low-stk",
                    created_at=now - timedelta(hours=28),
                )
            )

        adj_pending = StockAdjustment(
            tenant_id=tenant.id,
            shop_id=shop_west.id,
            product_id=product_by_sku["GEN-BAR"].id,
            quantity_delta=-5,
            reason_code="damage",
            notes="Shelf damage discovered during cycle count",
            status="pending",
            created_by=owner_admin_id,
            approved_by=None,
        )
        adj_approved = StockAdjustment(
            tenant_id=tenant.id,
            shop_id=shop_downtown.id,
            product_id=product_by_sku["OFF-NOTE"].id,
            quantity_delta=12,
            reason_code="recount",
            notes="Variance confirmed and corrected",
            status="approved",
            created_by=owner_admin_id,
            approved_by=owner_admin_id,
        )
        db.add_all([adj_pending, adj_approved])
        db.add(
            StockMovement(
                tenant_id=tenant.id,
                shop_id=shop_downtown.id,
                product_id=product_by_sku["OFF-NOTE"].id,
                quantity_delta=12,
                movement_type="adjustment",
                transaction_id=None,
                idempotency_key="showcase:adjustment:approved-off-note",
                created_at=now - timedelta(hours=12),
            )
        )

        transfer = TransferOrder(
            tenant_id=tenant.id,
            from_shop_id=shop_downtown.id,
            to_shop_id=shop_west.id,
            status="in_transit",
            created_by=owner_admin_id,
            completed_at=None,
        )
        db.add(transfer)
        db.flush()
        db.add(
            TransferOrderLine(
                transfer_order_id=transfer.id,
                product_id=product_by_sku["GEN-WATER"].id,
                quantity_requested=24,
                quantity_shipped=20,
                quantity_received=0,
            )
        )

        db.commit()

        print("Showcase demo reset complete. admin_users were preserved.")
        print(f"  tenant_id:           {tenant.id}")
        print(f"  slug:                {FIXED_SLUG}")
        print(f"  shop_downtown_id:    {shop_downtown.id}")
        print(f"  shop_westside_id:    {shop_west.id}")
        print(f"  products:            {len(products)}")
        print(f"  enrollment_token:    {raw_enrollment}")
        print("  Use cashier app → enroll with token above (Downtown Store).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
