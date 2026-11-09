"""Organization templates with versions and review (WP22.5), tenant-isolated from the start.

Revision ID: 0046
Revises: 0045
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_templates",
        sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)),
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id", "version", name="org_templates_pkey"),
    )
    for sql in enable_rls_sql("org_templates"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("org_templates")
