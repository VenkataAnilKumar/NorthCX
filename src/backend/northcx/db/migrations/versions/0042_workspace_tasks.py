"""Pilot tasks (E6), tenant-isolated from the start.

Revision ID: 0042
Revises: 0041
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_tasks",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)),
        sa.Column("owner", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.Column("data", JSONB, nullable=False),
    )
    op.create_index("ix_workspace_tasks_owner", "workspace_tasks", ["tenant_id", "owner", "created_at"])
    for sql in enable_rls_sql("workspace_tasks"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_index("ix_workspace_tasks_owner", table_name="workspace_tasks")
    op.drop_table("workspace_tasks")
