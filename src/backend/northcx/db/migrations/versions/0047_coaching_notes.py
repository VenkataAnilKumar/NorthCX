"""Coaching notes (E7), tenant-isolated from the start.

Revision ID: 0047
Revises: 0046
"""
import sqlalchemy as sa
from alembic import op

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coaching_notes",
        sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)),
        sa.Column("id", sa.String(16), nullable=False),
        sa.Column("session_id", sa.String(200), nullable=False),
        sa.Column("about", sa.String(80), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False),
        sa.Column("author", sa.String(200), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="coaching_notes_pkey"),
    )
    op.create_index("ix_coaching_notes_session_id", "coaching_notes", ["session_id"])
    for sql in enable_rls_sql("coaching_notes"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("coaching_notes")
