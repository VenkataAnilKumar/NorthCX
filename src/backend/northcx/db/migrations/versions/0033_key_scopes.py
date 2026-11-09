"""Keys limited to agents and environments (WP3.1). Existing keys stay unlimited (null).

Revision ID: 0033
Revises: 0032
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("agents", JSONB, nullable=True))
    op.add_column("api_keys", sa.Column("environments", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("api_keys", "environments")
    op.drop_column("api_keys", "agents")
