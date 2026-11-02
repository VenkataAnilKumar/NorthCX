"""Monitoring findings.

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitor_findings",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("rule", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("detail", sa.String(400), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("agent_version", sa.Integer, nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_monitor_created", "monitor_findings", ["created_at"])
    op.create_index("ix_monitor_rule", "monitor_findings", ["rule", "created_at"])
    op.create_index("ix_monitor_session", "monitor_findings", ["session_id"])


def downgrade() -> None:
    op.drop_table("monitor_findings")
