"""Outputs and spaces for the Workspace, tenant-isolated from the start.

Revision ID: 0050
Revises: 0049
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tid = lambda: sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL))  # noqa: E731
    op.create_table("workspace_outputs", tid(), sa.Column("id", sa.String(20), nullable=False), sa.Column("owner", sa.String(200), nullable=False), sa.Column("title", sa.String(120), nullable=False),
                    sa.Column("kind", sa.String(16), nullable=False), sa.Column("visibility", sa.String(10), nullable=False), sa.Column("space_id", sa.String(20), nullable=True),
                    sa.Column("source", sa.String(80), nullable=False), sa.Column("created_at", sa.Float, nullable=False), sa.Column("updated_at", sa.Float, nullable=False),
                    sa.Column("expires_at", sa.Float, nullable=False), sa.Column("data", JSONB, nullable=False), sa.PrimaryKeyConstraint("tenant_id", "id", name="workspace_outputs_pkey"))
    op.create_index("ix_workspace_outputs_space", "workspace_outputs", ["space_id"])
    op.create_index("ix_workspace_outputs_owner", "workspace_outputs", ["owner"])
    op.create_index("ix_workspace_outputs_expires", "workspace_outputs", ["expires_at"])
    op.create_table("workspace_spaces", tid(), sa.Column("id", sa.String(20), nullable=False), sa.Column("owner", sa.String(200), nullable=False), sa.Column("name", sa.String(80), nullable=False),
                    sa.Column("visibility", sa.String(10), nullable=False), sa.Column("created_at", sa.Float, nullable=False), sa.Column("updated_at", sa.Float, nullable=False),
                    sa.Column("data", JSONB, nullable=False), sa.PrimaryKeyConstraint("tenant_id", "id", name="workspace_spaces_pkey"))
    for table in ("workspace_outputs", "workspace_spaces"):
        for sql in enable_rls_sql(table):
            op.execute(sql)


def downgrade() -> None:
    op.drop_table("workspace_spaces")
    op.drop_table("workspace_outputs")
