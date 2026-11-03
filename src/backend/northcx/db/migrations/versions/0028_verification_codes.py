"""One-time identity codes (only keyed hashes; no codes and no addresses are stored).

Revision ID: 0028
Revises: 0027
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verification_codes",
        sa.Column("session_id", sa.String(200), primary_key=True),
        sa.Column("customer_id", sa.String(200), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("dest_hash", sa.String(64), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.Float, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("sends", JSONB, nullable=False),
        sa.Column("verified_until", sa.Float, nullable=True),
        sa.Column("updated_at", sa.Float, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("verification_codes")
