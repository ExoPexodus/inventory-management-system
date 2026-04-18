"""Wipe all data and load a rich demo dataset with an optional bootstrap admin user.

Combines the former seed_demo.py and reset_demo_showcase.py into a single script.

Use for demos / feature showcases. **Destructive**: deletes every tenant, user, and
related row, then rebuilds from scratch.

Run inside the API container / with DATABASE_URL set:

  IMS_DEMO_RESET_OK=1 python -m app.scripts.reset_demo_showcase

Optionally create an admin user for the tenant:

  IMS_DEMO_RESET_OK=1 ADMIN_BOOTSTRAP_EMAIL=admin@example.com ADMIN_BOOTSTRAP_PASSWORD=secret \\
    python -m app.scripts.reset_demo_showcase
"""

from __future__ import annotations

import os
import random
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.rls import set_rls_context
from app.db.session import SessionLocal
from app.models import (
    EnrollmentToken,
    PaymentAllocation,
    Permission,
    Product,
    ProductGroup,
    PurchaseOrder,
    PurchaseOrderLine,
    Role,
    RolePermission,
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
    User,
)
from app.services.enrollment import hash_token
from app.services.tax import sale_tax_totals


FIXED_SLUG = "showcase-demo"

# ---------------------------------------------------------------------------
# Hour-of-day weights for realistic peak patterns
# ---------------------------------------------------------------------------
_HOUR_WEIGHTS = {
    7: 3, 8: 12, 9: 14, 10: 9, 11: 10,
    12: 13, 13: 11, 14: 7, 15: 6,
    16: 8, 17: 12, 18: 10, 19: 6, 20: 4, 21: 2,
}
_HOURS = list(_HOUR_WEIGHTS.keys())
_HOUR_W = list(_HOUR_WEIGHTS.values())

# Weekday base transaction count (Mon=0 … Sun=6)
_WEEKDAY_BASE = {0: 10, 1: 10, 2: 12, 3: 13, 4: 18, 5: 20, 6: 8}

# Category probability by time bucket
# (beverages, grocery, stationery, apparel) — must sum to 1.0
_TIME_CATEGORY_WEIGHTS = {
    "morning":   (0.75, 0.25, 0.00, 0.00),
    "lunch":     (0.40, 0.30, 0.20, 0.10),
    "afternoon": (0.35, 0.25, 0.25, 0.15),
    "evening":   (0.30, 0.20, 0.25, 0.25),
}

_BEVERAGE_SKUS = ["SFT-LATTE", "SFT-AMER", "SFT-TEA"]
_BEVERAGE_W    = [40, 35, 25]
_GROCERY_SKUS  = ["GEN-WATER", "GEN-BAR"]
_GROCERY_W     = [55, 45]
_STATION_SKUS  = ["OFF-PEN", "OFF-NOTE", "LOW-STK"]
_STATION_W     = [50, 35, 15]
_APPAREL_SKUS  = ["APP-TOTE", "APP-HAT-M", "APP-HAT-S"]
_APPAREL_W     = [50, 35, 15]

_ITEM_COUNT_CHOICES = [1, 2, 3, 4]
_ITEM_COUNT_W       = [55, 30, 12, 3]
_QTY_CHOICES        = [1, 2, 3, 4]
_QTY_W              = [70, 20, 7, 3]


_ALL_PERMS = [
    "admin_web:access", "admin_mobile:access", "cashier_app:access",
    "staff:read", "staff:write",
    "catalog:read", "catalog:write",
    "inventory:read", "inventory:write",
    "procurement:read", "procurement:write",
    "sales:read", "sales:write",
    "analytics:read",
    "operations:read", "operations:write",
    "settings:read", "settings:write",
    "integrations:read", "integrations:write",
    "operators:read", "operators:write",
    "roles:read", "roles:write",
    "audit:read",
    "reports:read",
    "notifications:read", "notifications:write",
    "enrollment:write",
    "shops:read", "shops:write",
]
_MANAGER_PERMS = [
    "admin_web:access", "admin_mobile:access",
    "staff:read", "staff:write",
    "catalog:read", "catalog:write",
    "inventory:read", "inventory:write",
    "procurement:read", "procurement:write",
    "sales:read", "sales:write",
    "analytics:read",
    "operations:read", "operations:write",
    "notifications:read", "notifications:write",
    "audit:read",
    "reports:read",
    "shops:read",
]
_SYSTEM_ROLES = [
    ("owner",   "Owner",   _ALL_PERMS),
    ("manager", "Manager", _MANAGER_PERMS),
    ("cashier", "Cashier", ["cashier_app:access"]),
]


def _seed_system_roles(db: Session, tenant_id: UUID) -> None:
    """Create the three system roles for a tenant and wire up their permissions."""
    perm_rows = db.execute(select(Permission)).scalars().all()
    perm_map = {p.codename: p for p in perm_rows}
    for name, display_name, codenames in _SYSTEM_ROLES:
        role = Role(
            tenant_id=tenant_id,
            name=name,
            display_name=display_name,
            is_system=True,
        )
        db.add(role)
        db.flush()
        for codename in codenames:
            perm = perm_map.get(codename)
            if perm:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db.flush()


def _require_confirmation() -> None:
    if os.environ.get("IMS_DEMO_RESET_OK", "").strip() != "1":
        raise SystemExit(
            "Refusing to reset: set IMS_DEMO_RESET_OK=1 to confirm you want to delete all tenant data.\n"
            "Example: IMS_DEMO_RESET_OK=1 python -m app.scripts.reset_demo_showcase"
        )


def _wipe_all(db: Session) -> None:
    """Remove all users and tenants (CASCADE removes shops, products, transactions, etc.)."""
    set_rls_context(db, is_admin=True, tenant_id=None)
    # Delete users first — role_id has ON DELETE RESTRICT on roles, which are
    # tenant-scoped and would be CASCADE-deleted with the tenant. Removing users
    # first avoids a constraint violation regardless of cascade ordering.
    db.execute(text("DELETE FROM users"))
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


def _pick_hour(rng: random.Random) -> int:
    return rng.choices(_HOURS, weights=_HOUR_W, k=1)[0]


def _pick_sale_items(rng: random.Random, hour: int) -> list[tuple[str, int]]:
    """Return a list of (sku, qty) pairs for a single transaction."""
    if 7 <= hour <= 10:
        time_bucket = "morning"
    elif 11 <= hour <= 14:
        time_bucket = "lunch"
    elif 15 <= hour <= 17:
        time_bucket = "afternoon"
    else:
        time_bucket = "evening"

    cat_weights = _TIME_CATEGORY_WEIGHTS[time_bucket]
    n_items = rng.choices(_ITEM_COUNT_CHOICES, weights=_ITEM_COUNT_W, k=1)[0]

    chosen_skus: list[str] = []
    for _ in range(n_items):
        cat = rng.choices(
            ["beverages", "grocery", "stationery", "apparel"],
            weights=cat_weights,
            k=1,
        )[0]
        if cat == "beverages":
            sku = rng.choices(_BEVERAGE_SKUS, weights=_BEVERAGE_W, k=1)[0]
        elif cat == "grocery":
            sku = rng.choices(_GROCERY_SKUS, weights=_GROCERY_W, k=1)[0]
        elif cat == "stationery":
            sku = rng.choices(_STATION_SKUS, weights=_STATION_W, k=1)[0]
        else:
            sku = rng.choices(_APPAREL_SKUS, weights=_APPAREL_W, k=1)[0]
        chosen_skus.append(sku)

    # Merge duplicates (same product in one transaction = higher qty)
    merged: dict[str, int] = {}
    for sku in chosen_skus:
        qty = rng.choices(_QTY_CHOICES, weights=_QTY_W, k=1)[0]
        merged[sku] = merged.get(sku, 0) + qty

    return list(merged.items())


def main() -> None:
    _require_confirmation()
    raw_enrollment = secrets.token_urlsafe(24)
    rng = random.Random(42)
    db = SessionLocal()
    try:
        _wipe_all(db)
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

        _seed_system_roles(db, tenant.id)

        # -----------------------------------------------------------------------
        # Bootstrap admin user (optional — set env vars to enable)
        # -----------------------------------------------------------------------
        bootstrap_note = ""
        owner_admin_id: UUID | None = None
        em = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "").strip().lower()
        raw_pw = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "").strip()
        if em and raw_pw:
            owner_role = db.execute(
                select(Role).where(Role.tenant_id == tenant.id, Role.name == "owner")
            ).scalar_one_or_none()
            if owner_role is None:
                bootstrap_note = "  bootstrap_admin: skipped (no owner role found — run migrations first)"
            else:
                h = bcrypt.hashpw(raw_pw.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
                admin_user = User(
                    email=em,
                    password_hash=h,
                    role_id=owner_role.id,
                    tenant_id=tenant.id,
                    name=em.split("@", 1)[0].replace(".", " ").title(),
                    avatar_url=f"https://api.dicebear.com/9.x/identicon/svg?seed={em}",
                )
                db.add(admin_user)
                db.flush()
                owner_admin_id = admin_user.id
                bootstrap_note = f"  bootstrap_admin: created ({em})"

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
            ("SFT-AMER",  "Americano",         350,  "Beverages",  grp_bev.id,     "12 oz"),
            ("SFT-LATTE", "Latte",             495,  "Beverages",  grp_bev.id,     "16 oz"),
            ("SFT-TEA",   "Green tea",         275,  "Beverages",  grp_bev.id,     None),
            ("GEN-WATER", "Still water",       200,  "Grocery",    None,           None),
            ("GEN-BAR",   "Energy bar",        225,  "Grocery",    None,           None),
            ("APP-HAT-S", "Canvas cap",        1999, "Apparel",    grp_apparel.id, "S"),
            ("APP-HAT-M", "Canvas cap",        1999, "Apparel",    grp_apparel.id, "M"),
            ("APP-TOTE",  "Tote bag",          2495, "Apparel",    None,           None),
            ("OFF-NOTE",  "Desk notepad",      599,  "Stationery", None,           None),
            ("OFF-PEN",   "Gel pen 2pk",       449,  "Stationery", None,           None),
            ("LOW-STK",   "Promo sticker roll", 150, "Stationery", None,           None),
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
            ("Metro Roasters Co.",   "active",   "orders@metroroasters.test", "+1-555-0101", "Primary coffee beans"),
            ("Pacific Packaging",    "active",   "hello@pacificpack.test",    "+1-555-0102", None),
            ("QuickShip Logistics",  "active",   "ops@quickship.test",        None,          "Outbound freight"),
            ("Old Harbor Wholesale", "inactive", "archive@oldharbor.test",    None,          "Paused — seasonal only"),
        ]
        suppliers: list[Supplier] = []
        for name, st, em_addr, ph, notes in suppliers_data:
            supplier = Supplier(
                tenant_id=tenant.id,
                name=name,
                status=st,
                contact_email=em_addr,
                contact_phone=ph,
                notes=notes,
            )
            db.add(supplier)
            suppliers.append(supplier)
        db.flush()

        # Tax overrides
        tax_exempt = ShopProductTax(
            tenant_id=tenant.id,
            shop_id=shop_downtown.id,
            product_id=product_by_sku["SFT-AMER"].id,
            tax_exempt=True,
            effective_tax_rate_bps=None,
        )
        tax_custom = ShopProductTax(
            tenant_id=tenant.id,
            shop_id=shop_west.id,
            product_id=product_by_sku["SFT-LATTE"].id,
            tax_exempt=False,
            effective_tax_rate_bps=500,
        )
        db.add_all([tax_exempt, tax_custom])
        db.flush()

        tax_overrides_dd: dict[UUID, ShopProductTax] = {tax_exempt.product_id: tax_exempt}
        tax_overrides_west: dict[UUID, ShopProductTax] = {tax_custom.product_id: tax_custom}

        # Opening inventory — increased so stock survives 63 days of sales
        downtown_inv = {p.id: 300 for p in products}
        downtown_inv[product_by_sku["LOW-STK"].id] = 4
        west_inv = {p.id: 150 for p in products}
        west_inv[product_by_sku["LOW-STK"].id] = 3

        _add_opening_stock(db, tenant.id, shop_downtown.id, downtown_inv, "showcase-dd")
        _add_opening_stock(db, tenant.id, shop_west.id, west_inv, "showcase-ws")

        now = datetime.now(UTC)

        # -----------------------------------------------------------------------
        # 63 days of realistic transactions
        # -----------------------------------------------------------------------
        total_txns = 0
        for day_offset in range(63, 0, -1):
            day_dt = now - timedelta(days=day_offset)
            weekday = day_dt.weekday()
            txn_count = _WEEKDAY_BASE[weekday] + rng.randint(-2, 3)

            for i in range(txn_count):
                hour = _pick_hour(rng)
                minute = rng.randint(0, 59)
                when = day_dt.replace(
                    hour=hour,
                    minute=minute,
                    second=rng.randint(0, 59),
                    microsecond=0,
                    tzinfo=UTC,
                )
                shop = shop_downtown if rng.random() < 0.65 else shop_west
                tax_ov = tax_overrides_dd if shop is shop_downtown else tax_overrides_west
                tender = "card" if rng.random() < 0.65 else "cash"
                sku_qty = _pick_sale_items(rng, hour)

                _sale_txn(
                    db,
                    tenant_id=tenant.id,
                    shop=shop,
                    product_by_sku=product_by_sku,
                    sku_qty=sku_qty,
                    tender=tender,
                    when=when,
                    status="posted",
                    mutation_suffix=f"{day_offset}-{str(shop.id)[:4]}-{i}",
                    tax_overrides=tax_ov,
                )
                total_txns += 1

        # Pending sale (no stock deduction — in progress at cashier)
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

        # Refunded sale
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

        # Manual stock movements
        db.add(StockMovement(
            tenant_id=tenant.id,
            shop_id=shop_downtown.id,
            product_id=product_by_sku["OFF-NOTE"].id,
            quantity_delta=25,
            movement_type="receipt",
            transaction_id=None,
            idempotency_key="showcase:manual-receipt-1",
            created_at=now - timedelta(days=6),
        ))
        db.add(StockMovement(
            tenant_id=tenant.id,
            shop_id=shop_west.id,
            product_id=product_by_sku["GEN-BAR"].id,
            quantity_delta=-2,
            movement_type="shrink",
            transaction_id=None,
            idempotency_key="showcase:shrink-1",
            created_at=now - timedelta(days=4),
        ))

        db.add(EnrollmentToken(
            tenant_id=tenant.id,
            shop_id=shop_downtown.id,
            token_hash=hash_token(raw_enrollment),
            expires_at=datetime.now(UTC) + timedelta(days=14),
        ))

        # -----------------------------------------------------------------------
        # Procurement showcase data (5 POs spanning the period)
        # -----------------------------------------------------------------------
        main_supplier = suppliers[0]  # Metro Roasters

        # PO received ~45 days ago
        po_old_received = PurchaseOrder(
            tenant_id=tenant.id,
            supplier_id=main_supplier.id,
            status="received",
            expected_delivery_date=now - timedelta(days=46),
            notes="Initial bulk order — beverages",
            created_by_user_id=owner_admin_id,
            created_at=now - timedelta(days=50),
        )
        # PO received ~20 days ago
        po_mid_received = PurchaseOrder(
            tenant_id=tenant.id,
            supplier_id=suppliers[1].id,
            status="received",
            expected_delivery_date=now - timedelta(days=21),
            notes="Stationery restock — mid month",
            created_by_user_id=owner_admin_id,
            created_at=now - timedelta(days=24),
        )
        po_received = PurchaseOrder(
            tenant_id=tenant.id,
            supplier_id=main_supplier.id,
            status="received",
            expected_delivery_date=now - timedelta(days=1),
            notes="Received and stocked",
            created_by_user_id=owner_admin_id,
        )
        po_ordered = PurchaseOrder(
            tenant_id=tenant.id,
            supplier_id=main_supplier.id,
            status="ordered",
            expected_delivery_date=now + timedelta(days=1),
            notes="Urgent beverage restock",
            created_by_user_id=owner_admin_id,
        )
        po_draft = PurchaseOrder(
            tenant_id=tenant.id,
            supplier_id=main_supplier.id,
            status="draft",
            expected_delivery_date=now + timedelta(days=3),
            notes="Weekly replenishment draft",
            created_by_user_id=owner_admin_id,
        )
        db.add_all([po_old_received, po_mid_received, po_received, po_ordered, po_draft])
        db.flush()

        db.add_all([
            PurchaseOrderLine(
                purchase_order_id=po_old_received.id,
                product_id=product_by_sku["SFT-LATTE"].id,
                quantity_ordered=200, quantity_received=200, unit_cost_cents=270,
            ),
            PurchaseOrderLine(
                purchase_order_id=po_old_received.id,
                product_id=product_by_sku["SFT-AMER"].id,
                quantity_ordered=150, quantity_received=150, unit_cost_cents=220,
            ),
            PurchaseOrderLine(
                purchase_order_id=po_mid_received.id,
                product_id=product_by_sku["OFF-PEN"].id,
                quantity_ordered=100, quantity_received=100, unit_cost_cents=180,
            ),
            PurchaseOrderLine(
                purchase_order_id=po_mid_received.id,
                product_id=product_by_sku["OFF-NOTE"].id,
                quantity_ordered=80, quantity_received=80, unit_cost_cents=220,
            ),
            PurchaseOrderLine(
                purchase_order_id=po_received.id,
                product_id=product_by_sku["LOW-STK"].id,
                quantity_ordered=120, quantity_received=120, unit_cost_cents=45,
            ),
            PurchaseOrderLine(
                purchase_order_id=po_ordered.id,
                product_id=product_by_sku["SFT-LATTE"].id,
                quantity_ordered=80, quantity_received=0, unit_cost_cents=270,
            ),
            PurchaseOrderLine(
                purchase_order_id=po_draft.id,
                product_id=product_by_sku["OFF-PEN"].id,
                quantity_ordered=60, quantity_received=0, unit_cost_cents=180,
            ),
        ])

        # Receipt stock movement for the LOW-STK PO
        db.add(StockMovement(
            tenant_id=tenant.id,
            shop_id=shop_downtown.id,
            product_id=product_by_sku["LOW-STK"].id,
            quantity_delta=120,
            movement_type="receipt",
            transaction_id=None,
            idempotency_key="showcase:po-receive:low-stk",
            created_at=now - timedelta(hours=28),
        ))

        # Stock adjustments
        db.add_all([
            StockAdjustment(
                tenant_id=tenant.id,
                shop_id=shop_west.id,
                product_id=product_by_sku["GEN-BAR"].id,
                quantity_delta=-5,
                reason_code="damage",
                notes="Shelf damage discovered during cycle count",
                status="pending",
                created_by_user_id=owner_admin_id,
                approved_by_user_id=None,
            ),
            StockAdjustment(
                tenant_id=tenant.id,
                shop_id=shop_downtown.id,
                product_id=product_by_sku["OFF-NOTE"].id,
                quantity_delta=12,
                reason_code="recount",
                notes="Variance confirmed and corrected",
                status="approved",
                created_by_user_id=owner_admin_id,
                approved_by_user_id=owner_admin_id,
            ),
        ])
        db.add(StockMovement(
            tenant_id=tenant.id,
            shop_id=shop_downtown.id,
            product_id=product_by_sku["OFF-NOTE"].id,
            quantity_delta=12,
            movement_type="adjustment",
            transaction_id=None,
            idempotency_key="showcase:adjustment:approved-off-note",
            created_at=now - timedelta(hours=12),
        ))

        # Transfer order (in transit)
        transfer = TransferOrder(
            tenant_id=tenant.id,
            from_shop_id=shop_downtown.id,
            to_shop_id=shop_west.id,
            status="in_transit",
            created_by_user_id=owner_admin_id,
            completed_at=None,
        )
        db.add(transfer)
        db.flush()
        db.add(TransferOrderLine(
            transfer_order_id=transfer.id,
            product_id=product_by_sku["GEN-WATER"].id,
            quantity_requested=24,
            quantity_shipped=20,
            quantity_received=0,
        ))

        db.commit()

        print("Showcase demo reset complete.")
        print(f"  tenant_id:           {tenant.id}")
        print(f"  slug:                {FIXED_SLUG}")
        print(f"  shop_downtown_id:    {shop_downtown.id}")
        print(f"  shop_westside_id:    {shop_west.id}")
        print(f"  products:            {len(products)}")
        print(f"  transactions seeded: {total_txns} posted (+ 1 pending, 1 refunded)")
        print(f"  enrollment_token:    {raw_enrollment}")
        if bootstrap_note:
            print(bootstrap_note)
        print("  Use cashier app → enroll with token above (Downtown Store).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
