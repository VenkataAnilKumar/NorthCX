"""Tenants, channel bindings, and the tenant on keys and audit entries (WP2.2 and the first batch of WP2.3). Existing rows belong to 'default'.

Revision ID: 0037
Revises: 0036
"""
import time

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tenants = op.create_table(
        "tenants",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.bulk_insert(tenants, [{"id": "default", "name": "Default", "status": "active", "created_at": time.time()}])
    op.create_table(
        "channel_bindings",
        sa.Column("kind", sa.String(24), primary_key=True),
        sa.Column("address", sa.String(200), primary_key=True),
        sa.Column("tenant_id", sa.String(40), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_channel_bindings_tenant_id", "channel_bindings", ["tenant_id"])
    op.add_column("api_keys", sa.Column("tenant_id", sa.String(40), nullable=False, server_default="default"))
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.add_column("audit_log", sa.Column("tenant_id", sa.String(40), nullable=False, server_default="default"))
    op.create_index("ix_audit_tenant", "audit_log", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_audit_tenant", table_name="audit_log")
    op.drop_column("audit_log", "tenant_id")
    op.drop_index("ix_api_keys_tenant_id", table_name="api_keys")
    op.drop_column("api_keys", "tenant_id")
    op.drop_index("ix_channel_bindings_tenant_id", table_name="channel_bindings")
    op.drop_table("channel_bindings")
    op.drop_table("tenants")
