"""Phone calls handled by the voice channel (no audio, no phone numbers: only a hash of the caller's number).

Revision ID: 0026
Revises: 0025
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_calls",
        sa.Column("call_id", sa.String(100), primary_key=True),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("caller_hash", sa.String(64), nullable=False),
        sa.Column("started_at", sa.Float, nullable=False),
        sa.Column("ended_at", sa.Float, nullable=True),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("consent", sa.String(16), nullable=False),
        sa.Column("recorded", sa.Boolean, nullable=False),
        sa.Column("turns", sa.Integer, nullable=False),
        sa.Column("barge_ins", sa.Integer, nullable=False),
        sa.Column("languages", JSONB, nullable=False),
        sa.Column("handoff_id", sa.String(64), nullable=True),
        sa.Column("latency_ms", JSONB, nullable=False),
    )
    op.create_index("ix_voice_calls_started", "voice_calls", ["started_at"])
    op.create_index("ix_voice_calls_session", "voice_calls", ["session_id"])


def downgrade() -> None:
    op.drop_table("voice_calls")
