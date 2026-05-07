"""seed email:manage permission

Revision ID: 20260518000001
Revises: 20260517000001
Create Date: 2026-05-18 00:00:01

"""
from __future__ import annotations

from alembic import op

revision = "20260518000001"
down_revision = "20260517000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'email:manage', 'Manage Email Configuration', 'settings',
                'Configure transactional email settings and send test emails')
        ON CONFLICT (codename) DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = TRUE
          AND p.codename = 'email:manage'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE codename = 'email:manage')
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'email:manage'")
