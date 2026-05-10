"""Backfill NULL descriptions for customers:read and customers:write permissions.

Revision ID: 20260531000001
Revises: 20260530000001
Create Date: 2026-05-31 00:00:01
"""
from __future__ import annotations

from alembic import op

revision = "20260531000001"
down_revision = "20260530000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE permissions
        SET description = 'View customers and customer groups'
        WHERE codename = 'customers:read' AND description IS NULL
    """)
    op.execute("""
        UPDATE permissions
        SET description = 'Create, edit, and delete customers and customer groups'
        WHERE codename = 'customers:write' AND description IS NULL
    """)


def downgrade() -> None:
    pass  # backfill is non-destructive; downgrade is a no-op
