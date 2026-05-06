"""Seed business_type:manage permission

Revision ID: 20260514000002
Revises: 20260514000001
Create Date: 2026-05-14 00:00:02.000000
"""
from __future__ import annotations

from alembic import op

revision = "20260514000002"
down_revision = "20260514000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'business_type:manage', 'Manage Business Type', 'settings',
                'Set tenant business type and enable physical/online conversion')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'business_type:manage'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'business_type:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'business_type:manage'")
