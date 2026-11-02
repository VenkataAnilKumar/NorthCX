"""Approval resume: approval context and results, and the outbox.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approvals", sa.Column("agent_id", sa.String(200), nullable=False, server_default=""))
    op.add_column("approvals", sa.Column("customer_id", sa.String(200), nullable=True))
    op.add_column("approvals", sa.Column("note", sa.Text, nullable=True))
    op.add_column("approvals", sa.Column("result", JSONB, nullable=True))
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("delivered_at", sa.Float, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_outbox_session", "outbox", ["session_id", "id"])


def downgrade() -> None:
    op.drop_table("outbox")
    op.drop_column("approvals", "result")
    op.drop_column("approvals", "note")
    op.drop_column("approvals", "customer_id")
    op.drop_column("approvals", "agent_id")
