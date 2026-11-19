"""Connections to MCP servers and the tool definitions approved for each, tenant-isolated from the start.

Revision ID: 0057
Revises: 0056
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("mcp_connections", sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)), sa.Column("id", sa.String(16), nullable=False),
                    sa.Column("name", sa.String(24), nullable=False), sa.Column("url", sa.Text, nullable=False), sa.Column("trusted", sa.Boolean, nullable=False),
                    sa.Column("secret", sa.String(40), nullable=True), sa.Column("enabled", sa.Boolean, nullable=False), sa.Column("approved", JSONB, nullable=False),
                    sa.Column("created_by", sa.String(200), nullable=False), sa.Column("created_at", sa.Float, nullable=False), sa.Column("updated_by", sa.String(200), nullable=False),
                    sa.Column("updated_at", sa.Float, nullable=False), sa.PrimaryKeyConstraint("tenant_id", "id", name="mcp_connections_pkey"),
                    sa.UniqueConstraint("tenant_id", "name", name="uq_mcp_connections_name"))
    for sql in enable_rls_sql("mcp_connections"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("mcp_connections")
