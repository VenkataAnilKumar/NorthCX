"""Per-tenant sealed secrets, tenant-isolated from the start.

Revision ID: 0056
Revises: 0055
"""
import sqlalchemy as sa
from alembic import op

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("tenant_secrets", sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)), sa.Column("name", sa.String(40), nullable=False),
                    sa.Column("sealed", sa.Text, nullable=False), sa.Column("updated_by", sa.String(200), nullable=False), sa.Column("updated_at", sa.Float, nullable=False),
                    sa.PrimaryKeyConstraint("tenant_id", "name", name="tenant_secrets_pkey"))
    for sql in enable_rls_sql("tenant_secrets"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("tenant_secrets")
