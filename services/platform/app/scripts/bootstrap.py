"""Bootstrap the platform database with an initial operator, plans, and add-ons.

Usage:
    python -m app.scripts.bootstrap

Idempotent — skips records that already exist (matched by email/codename).
"""

from __future__ import annotations

import uuid

import bcrypt
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.tables import Addon, Plan, PlatformOperator


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


OPERATOR_EMAIL = "admin@platform.ims"
OPERATOR_PASSWORD = "admin"  # change in production
OPERATOR_NAME = "Platform Admin"

PLANS = [
    {
        "codename": "starter",
        "display_name": "Starter",
        "description": "Essential POS features for a single shop.",
        "base_price_cents": 99900,  # 999 INR/month
        "currency_code": "INR",
        "yearly_discount_pct": 20,
        "max_shops": 1,
        "max_employees": 5,
        "storage_limit_mb": 500,
    },
    {
        "codename": "growth",
        "display_name": "Growth",
        "description": "Multi-shop support with advanced features.",
        "base_price_cents": 249900,  # 2499 INR/month
        "currency_code": "INR",
        "yearly_discount_pct": 20,
        "max_shops": 3,
        "max_employees": 25,
        "storage_limit_mb": 2000,
    },
    {
        "codename": "enterprise",
        "display_name": "Enterprise",
        "description": "Unlimited shops, priority support, custom integrations.",
        "base_price_cents": 799900,  # 7999 INR/month
        "currency_code": "INR",
        "yearly_discount_pct": 25,
        "max_shops": 50,
        "max_employees": 200,
        "storage_limit_mb": 10000,
    },
]

ADDONS = [
    {
        "codename": "analytics",
        "display_name": "Analytics Dashboard",
        "description": "Revenue trends, category breakdowns, top products, and custom reports.",
        "price_cents": 49900,  # 499 INR/month
        "currency_code": "INR",
    },
    {
        "codename": "multi_shop",
        "display_name": "Multi-Shop",
        "description": "Manage inventory and staff across multiple locations.",
        "price_cents": 99900,
        "currency_code": "INR",
    },
    {
        "codename": "purchase_orders",
        "display_name": "Purchase Orders",
        "description": "Supplier management, purchase orders, and stock receiving.",
        "price_cents": 39900,
        "currency_code": "INR",
    },
    {
        "codename": "advanced_reporting",
        "display_name": "Advanced Reporting",
        "description": "Exportable audit trails, reconciliation, and shift reports.",
        "price_cents": 29900,
        "currency_code": "INR",
    },
    {
        "codename": "integrations",
        "display_name": "Integrations",
        "description": "Webhooks, API tokens, and third-party integrations.",
        "price_cents": 59900,
        "currency_code": "INR",
    },
]


def run() -> None:
    db = SessionLocal()
    try:
        # Operator
        existing_op = db.execute(
            select(PlatformOperator).where(PlatformOperator.email == OPERATOR_EMAIL)
        ).scalar_one_or_none()
        if existing_op is None:
            db.add(PlatformOperator(
                id=uuid.uuid4(),
                email=OPERATOR_EMAIL,
                password_hash=_hash(OPERATOR_PASSWORD),
                display_name=OPERATOR_NAME,
            ))
            print(f"Created operator: {OPERATOR_EMAIL} / {OPERATOR_PASSWORD}")
        else:
            print(f"Operator already exists: {OPERATOR_EMAIL}")

        # Plans
        for p in PLANS:
            exists = db.execute(
                select(Plan).where(Plan.codename == p["codename"])
            ).scalar_one_or_none()
            if exists is None:
                db.add(Plan(id=uuid.uuid4(), **p))
                print(f"Created plan: {p['codename']}")
            else:
                print(f"Plan already exists: {p['codename']}")

        # Addons
        for a in ADDONS:
            exists = db.execute(
                select(Addon).where(Addon.codename == a["codename"])
            ).scalar_one_or_none()
            if exists is None:
                db.add(Addon(id=uuid.uuid4(), **a))
                print(f"Created addon: {a['codename']}")
            else:
                print(f"Addon already exists: {a['codename']}")

        db.commit()
        print("\nBootstrap complete.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
