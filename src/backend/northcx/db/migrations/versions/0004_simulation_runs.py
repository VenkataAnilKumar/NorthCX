"""Stored simulation runs.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("passed", sa.Boolean, nullable=False),
        sa.Column("seconds", sa.Float, nullable=False),
        sa.Column("counts", JSONB, nullable=False),
        sa.Column("agent_digests", JSONB, nullable=False),
        sa.Column("meta", JSONB, nullable=False),
        sa.Column("results", JSONB, nullable=False),
    )
    op.create_index("ix_simulation_runs_created", "simulation_runs", ["created_at"])


def downgrade() -> None:
    op.drop_table("simulation_runs")
