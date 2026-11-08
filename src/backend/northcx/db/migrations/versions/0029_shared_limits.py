"""Shared rate counters and the daily token ledger, so several server processes enforce one limit.

Revision ID: 0029
Revises: 0028
"""
import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_counters",
        sa.Column("key", sa.String(300), primary_key=True),
        sa.Column("window_start", sa.BigInteger, primary_key=True),
        sa.Column("count", sa.Integer, nullable=False),
    )
    op.create_table(
        "usage_ledger",
        sa.Column("agent_id", sa.String(200), primary_key=True),
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("tokens", sa.BigInteger, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("usage_ledger")
    op.drop_table("rate_counters")
