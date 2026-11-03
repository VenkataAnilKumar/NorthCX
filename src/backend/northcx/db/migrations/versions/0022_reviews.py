"""Human reviews of conversations.

Revision ID: 0022
Revises: 0021
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_reviews",
        sa.Column("session_id", sa.String(200), primary_key=True),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("handoff", sa.String(16), nullable=False),
        sa.Column("failures", JSONB, nullable=False),
        sa.Column("note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("reviewer", sa.String(200), nullable=False),
        sa.Column("reviewed_at", sa.Float, nullable=False),
    )
    op.create_index("ix_reviews_at", "conversation_reviews", ["reviewed_at"])


def downgrade() -> None:
    op.drop_table("conversation_reviews")
