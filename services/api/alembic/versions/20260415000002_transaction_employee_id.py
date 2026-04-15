"""Add employee_id to transactions for cashier attribution

Revision ID: 20260415000002
Revises: 20260415000001
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa

revision = "20260415000002"
down_revision = "20260415000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column(
            "employee_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_transactions_employee_id",
        "transactions",
        ["employee_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_employee_id", table_name="transactions")
    op.drop_column("transactions", "employee_id")
