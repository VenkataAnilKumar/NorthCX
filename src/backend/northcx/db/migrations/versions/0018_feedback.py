"""Customer feedback on conversations, and an index for insights queries.

Revision ID: 0018
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_feedback",
        sa.Column("session_id", sa.String(200), primary_key=True),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_feedback_created", "conversation_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_table("conversation_feedback")
