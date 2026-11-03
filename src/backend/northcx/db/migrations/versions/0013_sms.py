"""SMS channel: sessions, messages, opt-outs.

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sms_sessions",
        sa.Column("session_id", sa.String(200), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("our_number", sa.String(20), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("last_seen", sa.Float, nullable=False),
    )
    op.create_index("ix_sms_sessions_phone", "sms_sessions", ["phone", "our_number", "last_seen"])
    op.create_table(
        "sms_messages",
        sa.Column("message_id", sa.String(400), primary_key=True),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("peer", sa.String(20), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_sms_messages_session", "sms_messages", ["session_id"])
    op.create_index("ix_sms_messages_peer", "sms_messages", ["peer", "direction", "created_at"])
    op.create_table(
        "sms_opt_outs",
        sa.Column("phone_hash", sa.String(64), primary_key=True),
        sa.Column("updated_at", sa.Float, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sms_opt_outs")
    op.drop_table("sms_messages")
    op.drop_table("sms_sessions")
