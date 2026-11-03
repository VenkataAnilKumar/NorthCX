"""Scenarios saved in the database by the scenario editor.

Revision ID: 0020
Revises: 0019
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "managed_scenarios",
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("required", sa.Boolean, nullable=False),
        sa.Column("definition", JSONB, nullable=False),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("updated_by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
    )
    op.create_index("ix_managed_scenarios_agent", "managed_scenarios", ["agent_id"])


def downgrade() -> None:
    op.drop_table("managed_scenarios")
