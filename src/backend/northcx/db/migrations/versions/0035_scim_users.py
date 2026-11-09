"""People provisioned by SCIM (WP3.3).

Revision ID: 0035
Revises: 0034
"""
import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scim_users",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("user_name", sa.String(200), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scim_users")
