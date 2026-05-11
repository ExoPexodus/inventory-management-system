"""rma exchange fulfillment tracking

Adds exchange_shipped_at, exchange_tracking_number, exchange_carrier_name to
refund_requests so the merchant can record replacement shipment for exchange-
type RMAs. Adds 'exchange_shipped' as a valid status (no schema enum — just
documentation of the value used by the application).

Revision ID: 20260603000001
Revises: 20260602000001
Create Date: 2026-05-11 00:00:01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260603000001"
down_revision = "20260602000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refund_requests",
        sa.Column("exchange_shipped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "refund_requests",
        sa.Column("exchange_tracking_number", sa.String(255), nullable=True),
    )
    op.add_column(
        "refund_requests",
        sa.Column("exchange_carrier_name", sa.String(128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("refund_requests", "exchange_carrier_name")
    op.drop_column("refund_requests", "exchange_tracking_number")
    op.drop_column("refund_requests", "exchange_shipped_at")
