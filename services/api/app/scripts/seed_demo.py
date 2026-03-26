"""Create demo tenant, shop, products, starting stock, and print a one-time enrollment token.

If ``ADMIN_BOOTSTRAP_EMAIL`` / ``ADMIN_BOOTSTRAP_PASSWORD`` are set but that email already exists
in ``admin_users``, the bootstrap admin row is skipped (no duplicate error).

Run from services/api with DATABASE_URL set:
  python -m app.scripts.seed_demo
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import os

import bcrypt
from sqlalchemy import select

from app.db.rls import set_rls_context
from app.db.session import SessionLocal
from app.models import (
    AdminUser,
    EnrollmentToken,
    Product,
    ProductGroup,
    Shop,
    StockMovement,
    Supplier,
    Tenant,
)
from app.services.enrollment import hash_token


def main() -> None:
    raw_token = secrets.token_urlsafe(24)
    db = SessionLocal()
    try:
        set_rls_context(db, is_admin=True, tenant_id=None)
        tenant = Tenant(
            name="Demo Retail",
            slug=f"demo-{uuid.uuid4().hex[:10]}",
        )
        db.add(tenant)
        db.flush()

        shop = Shop(tenant_id=tenant.id, name="Main Store", default_tax_rate_bps=825)
        db.add(shop)
        db.flush()

        notebook_grp = ProductGroup(tenant_id=tenant.id, title="Notebook", notes="Demo product group for variants")
        db.add(notebook_grp)
        db.flush()

        products_data = [
            ("SKU-001A", "Notebook", 500, "Stationery", notebook_grp.id, "Large · 8x10"),
            ("SKU-001B", "Notebook", 100, "Stationery", notebook_grp.id, "Small · pocket"),
            ("SKU-002", "Pen pack", 450, "Stationery", None, None),
            ("SKU-003", "Coffee mug", 1200, "Houseware", None, None),
        ]
        pids: list[uuid.UUID] = []
        for sku, name, price, category, group_id, variant_label in products_data:
            p = Product(
                tenant_id=tenant.id,
                product_group_id=group_id,
                sku=sku,
                name=name,
                category=category,
                unit_price_cents=price,
                variant_label=variant_label,
            )
            db.add(p)
            db.flush()
            pids.append(p.id)

        for pid in pids:
            db.add(
                StockMovement(
                    tenant_id=tenant.id,
                    shop_id=shop.id,
                    product_id=pid,
                    quantity_delta=100,
                    movement_type="adjustment",
                    transaction_id=None,
                    idempotency_key=f"seed:{pid}",
                )
            )

        db.add(
            Supplier(
                tenant_id=tenant.id,
                name="Acme Wholesale",
                status="active",
                contact_email="orders@acme.test",
                contact_phone="+1-555-0100",
            )
        )
        db.add(
            Supplier(
                tenant_id=tenant.id,
                name="Northwind Traders",
                status="active",
                contact_email="nw@northwind.test",
            )
        )

        db.add(
            EnrollmentToken(
                tenant_id=tenant.id,
                shop_id=shop.id,
                token_hash=hash_token(raw_token),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )

        em = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "").strip().lower()
        raw_pw = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "").strip()
        bootstrap_note = ""
        if em and raw_pw:
            existing = db.execute(select(AdminUser.id).where(AdminUser.email == em)).scalar_one_or_none()
            if existing is not None:
                bootstrap_note = f"  bootstrap_admin: skipped (already exists: {em})"
            else:
                h = bcrypt.hashpw(raw_pw.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
                db.add(AdminUser(email=em, password_hash=h, role="superadmin"))
                bootstrap_note = f"  bootstrap_admin: created ({em})"

        db.commit()

        print("Demo data created.")
        print(f"  tenant_id:  {tenant.id}")
        print(f"  shop_id:    {shop.id}")
        print(f"  enrollment_token (paste in app / QR payload): {raw_token}")
        if bootstrap_note:
            print(bootstrap_note)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
