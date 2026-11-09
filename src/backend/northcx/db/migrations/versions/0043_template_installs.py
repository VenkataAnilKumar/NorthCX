"""Agent Hub install records (E22), tenant-isolated from the start.

Revision ID: 0043
Revises: 0042
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "template_installs",
        sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("installed_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "agent_id", name="template_installs_pkey"),
    )
    for sql in enable_rls_sql("template_installs"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("template_installs")
