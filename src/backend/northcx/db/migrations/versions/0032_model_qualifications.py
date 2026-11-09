"""Model qualifications per agent (WP1.11).

Revision ID: 0032
Revises: 0031
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_qualifications",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("model", sa.String(300), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("result", JSONB, nullable=False),
    )
    op.create_index("ix_model_qualifications_agent_id", "model_qualifications", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_model_qualifications_agent_id", table_name="model_qualifications")
    op.drop_table("model_qualifications")
