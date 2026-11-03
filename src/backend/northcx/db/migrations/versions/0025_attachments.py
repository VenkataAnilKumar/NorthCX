"""Attachments customers send in a conversation.

Revision ID: 0025
Revises: 0024
"""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("media_type", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("uploaded_by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_attachments_session", "attachments", ["session_id"])


def downgrade() -> None:
    op.drop_table("attachments")
