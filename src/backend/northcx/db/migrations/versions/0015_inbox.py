"""Inbox integration: queued hand-off deliveries.

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbox_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("handoff_id", sa.String(64), nullable=False),
        sa.Column("connector", sa.String(32), nullable=False),
        sa.Column("event", sa.String(16), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.Float, nullable=True),
        sa.Column("delivered_at", sa.Float, nullable=True),
        sa.Column("external_ref", sa.String(200), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
    )
    op.create_index("ix_inbox_events_handoff", "inbox_events", ["handoff_id"])
    op.create_index("ix_inbox_events_pending", "inbox_events", ["delivered_at", "created_at"])


def downgrade() -> None:
    op.drop_table("inbox_events")
