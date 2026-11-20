"""Replies the agent wrote in shadow mode, waiting for a person to send, edit or reject them; tenant-isolated from the start.

Revision ID: 0058
Revises: 0057
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("shadow_drafts", sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)), sa.Column("id", sa.String(64), nullable=False),
                    sa.Column("session_id", sa.String(200), nullable=False), sa.Column("agent_id", sa.String(200), nullable=False), sa.Column("agent_version", sa.Integer, nullable=True),
                    sa.Column("customer_id", sa.String(200), nullable=True), sa.Column("trace_id", sa.String(64), nullable=False), sa.Column("customer_message", sa.Text, nullable=False),
                    sa.Column("draft", sa.Text, nullable=False), sa.Column("state", sa.String(16), nullable=False), sa.Column("final_text", sa.Text, nullable=True),
                    sa.Column("reasons", JSONB, nullable=False), sa.Column("note", sa.Text, nullable=True), sa.Column("decided_by", sa.String(200), nullable=True),
                    sa.Column("decided_at", sa.Float, nullable=True), sa.Column("created_at", sa.Float, nullable=False),
                    sa.PrimaryKeyConstraint("tenant_id", "id", name="shadow_drafts_pkey"))
    op.create_index("ix_shadow_drafts_state", "shadow_drafts", ["tenant_id", "state"])
    op.create_index("ix_shadow_drafts_session", "shadow_drafts", ["tenant_id", "session_id"])
    for sql in enable_rls_sql("shadow_drafts"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("shadow_drafts")
