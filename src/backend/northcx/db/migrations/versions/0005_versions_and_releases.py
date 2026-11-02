"""Agent versions, releases, and the agent version on traces.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("traces", sa.Column("agent_version", sa.Integer, nullable=True))
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("spec", JSONB, nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("author", sa.String(200), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.UniqueConstraint("agent_id", "number", name="uq_agent_versions_number"),
    )
    op.create_table(
        "releases",
        sa.Column("seq", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("id", sa.String(64), nullable=False, unique=True),
        sa.Column("agent_id", sa.String(200), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("version_id", sa.String(64), sa.ForeignKey("agent_versions.id"), nullable=True),
        sa.Column("number", sa.Integer, nullable=True),
        sa.Column("previous_number", sa.Integer, nullable=True),
        sa.Column("by", sa.String(200), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("gate", JSONB, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_releases_agent_env", "releases", ["agent_id", "environment", "seq"])


def downgrade() -> None:
    op.drop_table("releases")
    op.drop_table("agent_versions")
    op.drop_column("traces", "agent_version")
