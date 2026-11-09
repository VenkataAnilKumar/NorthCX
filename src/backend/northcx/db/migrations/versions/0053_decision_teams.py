"""Which team answered a hand-off or approval, tenant-isolated from the start.

Revision ID: 0053
Revises: 0052
"""
import sqlalchemy as sa
from alembic import op

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("decision_teams", sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)), sa.Column("kind", sa.String(10), nullable=False),
                    sa.Column("item_id", sa.String(64), nullable=False), sa.Column("team", sa.String(80), nullable=False), sa.Column("at", sa.Float, nullable=False),
                    sa.PrimaryKeyConstraint("tenant_id", "kind", "item_id", name="decision_teams_pkey"))
    for sql in enable_rls_sql("decision_teams"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("decision_teams")
