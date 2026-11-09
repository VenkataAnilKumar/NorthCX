"""Files kept in spaces, tenant-isolated from the start.

Revision ID: 0054
Revises: 0053
"""
import sqlalchemy as sa
from alembic import op

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("space_files", sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)), sa.Column("id", sa.String(20), nullable=False),
                    sa.Column("space_id", sa.String(20), nullable=False), sa.Column("name", sa.String(100), nullable=False), sa.Column("owner", sa.String(200), nullable=False),
                    sa.Column("created_at", sa.Float, nullable=False), sa.Column("text", sa.Text, nullable=False), sa.PrimaryKeyConstraint("tenant_id", "id", name="space_files_pkey"))
    op.create_index("ix_space_files_space", "space_files", ["space_id"])
    for sql in enable_rls_sql("space_files"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("space_files")
