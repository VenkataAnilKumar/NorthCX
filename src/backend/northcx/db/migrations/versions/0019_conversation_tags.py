"""Tags on conversations for review and filtering.

Revision ID: 0019
Revises: 0018
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_tags",
        sa.Column("session_id", sa.String(200), primary_key=True),
        sa.Column("tag", sa.String(40), primary_key=True),
        sa.Column("by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_tags_tag", "conversation_tags", ["tag"])


def downgrade() -> None:
    op.drop_table("conversation_tags")
