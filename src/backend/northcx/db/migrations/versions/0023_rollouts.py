"""Staged rollouts and their conversation assignments.

Revision ID: 0023
Revises: 0022
"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rollouts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("candidate_number", sa.Integer, nullable=False),
        sa.Column("control_number", sa.Integer, nullable=True),
        sa.Column("percent", sa.Integer, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("started_by", sa.String(200), nullable=False),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("ended_by", sa.String(200), nullable=True),
        sa.Column("started_at", sa.Float, nullable=False),
        sa.Column("ended_at", sa.Float, nullable=True),
    )
    op.create_index("uq_rollouts_active", "rollouts", ["agent_id", "environment"], unique=True, postgresql_where=sa.text("state = 'active'"))
    op.create_table(
        "rollout_assignments",
        sa.Column("rollout_id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(200), primary_key=True),
        sa.Column("arm", sa.String(16), nullable=False),
    )
    op.create_index("ix_rollout_assign_session", "rollout_assignments", ["session_id"])


def downgrade() -> None:
    op.drop_table("rollout_assignments")
    op.drop_table("rollouts")
