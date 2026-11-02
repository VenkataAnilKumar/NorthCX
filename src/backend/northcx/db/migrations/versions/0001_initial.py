"""Initial schema: sessions, messages, customer facts, traces, approvals.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("session_id", sa.String(200), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.UniqueConstraint("session_id", "seq", name="uq_messages_session_seq"),
    )
    op.create_table(
        "customer_facts",
        sa.Column("customer_id", sa.String(200), primary_key=True),
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "traces",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.Float, nullable=True),
        sa.Column("tools", JSONB, nullable=False),
        sa.Column("event_count", sa.Integer, nullable=False),
    )
    op.create_index("ix_traces_session", "traces", ["session_id"])
    op.create_index("ix_traces_started", "traces", ["started_at"])
    op.create_table(
        "trace_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("trace_id", sa.String(64), sa.ForeignKey("traces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("t", sa.Float, nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.UniqueConstraint("trace_id", "seq", name="uq_trace_events_seq"),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("tool", sa.String(200), nullable=False),
        sa.Column("input", JSONB, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("decided_by", sa.String(200), nullable=True),
        sa.Column("decided_at", sa.Float, nullable=True),
    )
    op.create_index("ix_approvals_state", "approvals", ["state"])


def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_table("trace_events")
    op.drop_table("traces")
    op.drop_table("customer_facts")
    op.drop_table("messages")
    op.drop_table("sessions")
