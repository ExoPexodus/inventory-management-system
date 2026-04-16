"""Add billing detail columns to tenants

Revision ID: 20260416000002
Revises: 20260416000001
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa

revision = "20260416000002"
down_revision = "20260416000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("billing_company_name", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("billing_gstin", sa.String(20), nullable=True))
    op.add_column("tenants", sa.Column("billing_address_line1", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("billing_address_line2", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("billing_city", sa.String(128), nullable=True))
    op.add_column("tenants", sa.Column("billing_state", sa.String(128), nullable=True))
    op.add_column("tenants", sa.Column("billing_postal_code", sa.String(20), nullable=True))
    op.add_column("tenants", sa.Column("billing_country", sa.String(64), nullable=True))


def downgrade() -> None:
    for col in ["billing_country", "billing_postal_code", "billing_state", "billing_city",
                 "billing_address_line2", "billing_address_line1", "billing_gstin", "billing_company_name"]:
        op.drop_column("tenants", col)
