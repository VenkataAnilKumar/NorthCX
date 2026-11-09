"""Staff notes about customers, tenant-isolated from the start.

Revision ID: 0048
Revises: 0047
"""
import sqlalchemy as sa
from alembic import op

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_notes",
        sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)),
        sa.Column("id", sa.String(16), nullable=False),
        sa.Column("customer_id", sa.String(200), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False),
        sa.Column("author", sa.String(200), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="customer_notes_pkey"),
    )
    op.create_index("ix_customer_notes_customer_id", "customer_notes", ["customer_id"])
    for sql in enable_rls_sql("customer_notes"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("customer_notes")
