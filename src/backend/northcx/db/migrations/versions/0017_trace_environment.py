"""Which environment answered a conversation turn.

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("traces", sa.Column("environment", sa.String(32), nullable=False, server_default="production"))


def downgrade() -> None:
    op.drop_column("traces", "environment")
