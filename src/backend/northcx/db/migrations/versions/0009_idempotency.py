"""Idempotency keys for API writes.

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("scope", sa.String(64), primary_key=True),
        sa.Column("req_hash", sa.String(64), nullable=False),
        sa.Column("response", JSONB, nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_idempotency_created", "idempotency_keys", ["created_at"])


def downgrade() -> None:
    op.drop_table("idempotency_keys")
