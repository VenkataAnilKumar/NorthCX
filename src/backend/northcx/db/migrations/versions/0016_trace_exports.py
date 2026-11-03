"""Trace export queue.

Revision ID: 0016
Revises: 0015
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trace_exports",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("exporter", sa.String(32), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.Float, nullable=True),
        sa.Column("delivered_at", sa.Float, nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
    )
    op.create_index("ix_trace_exports_trace", "trace_exports", ["trace_id"])
    op.create_index("ix_trace_exports_pending", "trace_exports", ["delivered_at", "created_at"])


def downgrade() -> None:
    op.drop_table("trace_exports")
