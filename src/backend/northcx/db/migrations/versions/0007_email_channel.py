"""Email channel: threads, messages, and outbox retry timing.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outbox", sa.Column("last_attempt_at", sa.Float, nullable=True))
    op.create_table(
        "email_sessions",
        sa.Column("session_id", sa.String(200), primary_key=True),
        sa.Column("sender", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("customer_id", sa.String(200), nullable=True),
        sa.Column("verified", sa.Boolean, nullable=False),
        sa.Column("last_message_id", sa.String(998), nullable=False),
        sa.Column("references", JSONB, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_email_sessions_sender", "email_sessions", ["sender"])
    op.create_table(
        "email_messages",
        sa.Column("message_id", sa.String(998), primary_key=True),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("peer", sa.String(320), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_email_messages_session", "email_messages", ["session_id"])
    op.create_index("ix_email_messages_peer", "email_messages", ["peer", "direction", "created_at"])


def downgrade() -> None:
    op.drop_table("email_messages")
    op.drop_table("email_sessions")
    op.drop_column("outbox", "last_attempt_at")
