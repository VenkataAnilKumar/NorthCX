"""State that used to live in one process: job leases, firing alerts and alert events, crawl jobs.

Revision ID: 0030
Revises: 0029
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_leases",
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("holder", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.Float, nullable=False),
    )
    op.create_table(
        "alert_state",
        sa.Column("rule", sa.String(100), primary_key=True),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_table(
        "alert_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("at", sa.Float, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_table(
        "crawl_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("source_id", sa.String(200), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("started_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index("ix_crawl_jobs_source_state", "crawl_jobs", ["source_id", "state"])
    op.create_index("ix_crawl_jobs_started", "crawl_jobs", ["started_at"])


def downgrade() -> None:
    op.drop_table("crawl_jobs")
    op.drop_table("alert_events")
    op.drop_table("alert_state")
    op.drop_table("job_leases")
