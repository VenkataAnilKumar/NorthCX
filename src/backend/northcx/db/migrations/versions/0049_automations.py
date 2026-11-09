"""Automations (routines), their runs and schedule state, tenant-isolated from the start.

Revision ID: 0049
Revises: 0048
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tid = lambda: sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL))  # noqa: E731
    op.create_table("automations", tid(), sa.Column("id", sa.String(40), nullable=False), sa.Column("version", sa.Integer, nullable=False), sa.Column("status", sa.String(16), nullable=False),
                    sa.Column("name", sa.String(80), nullable=False), sa.Column("created_at", sa.Float, nullable=False), sa.Column("updated_at", sa.Float, nullable=False),
                    sa.Column("data", JSONB, nullable=False), sa.PrimaryKeyConstraint("tenant_id", "id", "version", name="automations_pkey"))
    op.create_table("automation_runs", tid(), sa.Column("id", sa.String(20), nullable=False), sa.Column("automation_id", sa.String(40), nullable=False), sa.Column("status", sa.String(16), nullable=False),
                    sa.Column("started_at", sa.Float, nullable=False), sa.Column("data", JSONB, nullable=False), sa.PrimaryKeyConstraint("tenant_id", "id", name="automation_runs_pkey"))
    op.create_index("ix_automation_runs_auto", "automation_runs", ["automation_id", "started_at"])
    op.create_table("automation_state", tid(), sa.Column("automation_id", sa.String(40), nullable=False), sa.Column("next_run", sa.Float, nullable=True),
                    sa.Column("paused", sa.Boolean, nullable=False, server_default=sa.false()), sa.PrimaryKeyConstraint("tenant_id", "automation_id", name="automation_state_pkey"))
    for table in ("automations", "automation_runs", "automation_state"):
        for sql in enable_rls_sql(table):
            op.execute(sql)


def downgrade() -> None:
    for table in ("automation_state", "automation_runs", "automations"):
        op.drop_table(table)
