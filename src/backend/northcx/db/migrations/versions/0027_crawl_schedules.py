"""Scheduled re-crawls of allowed websites into knowledge sources.

Revision ID: 0027
Revises: 0026
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crawl_schedules",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("source_id", sa.String(200), sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("every_hours", sa.Float, nullable=False),
        sa.Column("next_run", sa.Float, nullable=False),
        sa.Column("last_run", sa.Float, nullable=True),
        sa.Column("last_job_id", sa.String(40), nullable=True),
        sa.Column("last_result", sa.String(300), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_index("ix_crawl_schedules_due", "crawl_schedules", ["enabled", "next_run"])


def downgrade() -> None:
    op.drop_index("ix_crawl_schedules_due", table_name="crawl_schedules")
    op.drop_table("crawl_schedules")
