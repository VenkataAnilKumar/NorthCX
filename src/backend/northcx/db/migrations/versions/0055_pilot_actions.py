"""Actions the Pilot proposed, tenant-isolated from the start.

Revision ID: 0055
Revises: 0054
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("pilot_actions", sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)), sa.Column("id", sa.String(20), nullable=False),
                    sa.Column("owner", sa.String(200), nullable=False), sa.Column("chat_id", sa.String(64), nullable=False), sa.Column("tool", sa.String(40), nullable=False),
                    sa.Column("state", sa.String(12), nullable=False), sa.Column("created_at", sa.Float, nullable=False), sa.Column("data", JSONB, nullable=False),
                    sa.PrimaryKeyConstraint("tenant_id", "id", name="pilot_actions_pkey"))
    op.create_index("ix_pilot_actions_owner", "pilot_actions", ["owner", "chat_id"])
    for sql in enable_rls_sql("pilot_actions"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("pilot_actions")
