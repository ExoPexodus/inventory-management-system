"""plan_features table + tenant_limit_overrides value_json column

Revision ID: 20260601000001
Revises: cda681b0bf46
Create Date: 2026-06-01
"""
from __future__ import annotations

import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260601000001"
down_revision = "cda681b0bf46"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# PLAN_FEATURES literal — copied verbatim from services/api/app/billing/plans.py
# so the migration can seed the platform DB without importing from another service.
# ---------------------------------------------------------------------------
PLAN_FEATURES: dict[str, dict] = {
    "trial": {
        "max_channels": 5,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "headless_api": True,
        "hosted_checkout": True,
        "byo_stripe": True,
        "byo_razorpay": True,
        "byo_paypal": True,
        "max_products": 1000,
        "multi_currency_advanced": True,
        "ai_product_generation": True,
        "email_volume_per_month": 5000,
    },
    "free": {
        "max_channels": 1,
    },
    "starter": {
        "max_channels": 2,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "max_products": 500,
        "byo_stripe": True,
        "email_volume_per_month": 1000,
    },
    "pro": {
        "max_channels": 5,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "headless_api": True,
        "hosted_checkout": True,
        "byo_stripe": True,
        "byo_razorpay": True,
        "byo_paypal": True,
        "max_products": 5000,
        "multi_currency_advanced": True,
        "email_volume_per_month": 10000,
    },
    "business": {
        "max_channels": 20,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "headless_api": True,
        "hosted_checkout": True,
        "byo_stripe": True,
        "byo_razorpay": True,
        "byo_paypal": True,
        "max_products": 50000,
        "multi_currency_advanced": True,
        "ai_product_generation": True,
        "email_volume_per_month": 100000,
    },
}


def upgrade() -> None:
    # 1. Create plan_features table
    op.create_table(
        "plan_features",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", UUID(as_uuid=True), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_key", sa.String(128), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("plan_id", "feature_key", name="uq_plan_features_plan_key"),
    )
    op.create_index("ix_plan_features_plan", "plan_features", ["plan_id"])

    # 2. Seed plan_features from the PLAN_FEATURES dict above
    conn = op.get_bind()
    for codename, features in PLAN_FEATURES.items():
        row = conn.execute(
            sa.text("SELECT id FROM plans WHERE codename = :codename"),
            {"codename": codename},
        ).fetchone()
        if row is None:
            # Plan not in DB — skip (e.g. "trial" / "free" may not exist in prod)
            continue
        plan_id = row[0]
        for feature_key, value in features.items():
            conn.execute(
                sa.text(
                    "INSERT INTO plan_features (id, plan_id, feature_key, value) "
                    "VALUES (:id, :plan_id, :feature_key, CAST(:value AS jsonb)) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "plan_id": str(plan_id),
                    "feature_key": feature_key,
                    "value": json.dumps(value),
                },
            )

    # 3. Add value_json column to tenant_limit_overrides
    op.add_column(
        "tenant_limit_overrides",
        sa.Column("value_json", JSONB, nullable=True),
    )

    # 4. Backfill: wrap existing int limit_value into value_json
    op.execute(
        "UPDATE tenant_limit_overrides "
        "SET value_json = jsonb_build_object('value', limit_value) "
        "WHERE value_json IS NULL"
    )


def downgrade() -> None:
    op.drop_column("tenant_limit_overrides", "value_json")
    op.drop_index("ix_plan_features_plan", table_name="plan_features")
    op.drop_table("plan_features")
