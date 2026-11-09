"""Release requests: the two-person rule for publishing (WP3.5).

Revision ID: 0036
Revises: 0035
"""
import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_requests",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer, nullable=True),
        sa.Column("requested_by", sa.String(200), nullable=False),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(200), nullable=True),
        sa.Column("decision_note", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("decided_at", sa.Float, nullable=True),
    )
    op.create_index("ix_release_requests_agent_id", "release_requests", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_release_requests_agent_id", table_name="release_requests")
    op.drop_table("release_requests")
