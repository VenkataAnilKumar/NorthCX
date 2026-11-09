"""Library items for staff, tenant-isolated from the start.

Revision ID: 0052
Revises: 0051
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("library_items", sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)), sa.Column("id", sa.String(20), nullable=False),
                    sa.Column("owner", sa.String(200), nullable=False), sa.Column("title", sa.String(120), nullable=False), sa.Column("kind", sa.String(10), nullable=False),
                    sa.Column("visibility", sa.String(10), nullable=False), sa.Column("uses", sa.Integer, nullable=False, server_default="0"), sa.Column("created_at", sa.Float, nullable=False),
                    sa.Column("updated_at", sa.Float, nullable=False), sa.Column("data", JSONB, nullable=False), sa.PrimaryKeyConstraint("tenant_id", "id", name="library_items_pkey"))
    op.create_index("ix_library_items_owner", "library_items", ["owner"])
    for sql in enable_rls_sql("library_items"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("library_items")
