"""Handoff queue.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "handoffs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("customer_id", sa.String(200), nullable=True),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("topics", JSONB, nullable=False),
        sa.Column("package", JSONB, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("resolved_by", sa.String(200), nullable=True),
        sa.Column("resolved_at", sa.Float, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
    )
    op.create_index("ix_handoffs_state", "handoffs", ["state", "created_at"])
    op.create_index("ix_handoffs_session", "handoffs", ["session_id"])


def downgrade() -> None:
    op.drop_table("handoffs")
