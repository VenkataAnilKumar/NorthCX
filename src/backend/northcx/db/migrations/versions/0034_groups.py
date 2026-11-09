"""Groups with roles (WP3.2), and the roles a sign-in session got from them.

Revision ID: 0034
Revises: 0033
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("extra_roles", JSONB, nullable=True))
    op.create_table(
        "groups",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("external_name", sa.String(200), nullable=True, unique=True),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("roles", JSONB, nullable=False),
        sa.Column("members", JSONB, nullable=False),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("groups")
    op.drop_column("api_keys", "extra_roles")
