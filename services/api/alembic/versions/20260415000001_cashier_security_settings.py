"""Cashier security: add employee_session_timeout_minutes to tenants

Revision ID: 20260415000001
Revises: 20260412000001
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa

revision = "20260415000001"
down_revision = "20260412000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "employee_session_timeout_minutes",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "employee_session_timeout_minutes")
