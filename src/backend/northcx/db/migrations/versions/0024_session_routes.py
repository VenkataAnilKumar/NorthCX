"""Which agent each conversation is currently with, after transfers between agents.

Revision ID: 0024
Revises: 0023
"""
import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_routes",
        sa.Column("session_id", sa.String(200), primary_key=True),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("session_routes")
