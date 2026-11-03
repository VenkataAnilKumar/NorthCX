"""Long-term customer memories.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_memories",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("customer_id", sa.String(200), nullable=False),
        sa.Column("text", sa.String(300), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("source_session", sa.String(200), nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.UniqueConstraint("customer_id", "text_hash", name="uq_memory_fact"),
    )
    op.execute("ALTER TABLE customer_memories ADD COLUMN tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED")
    op.create_index("ix_memories_customer", "customer_memories", ["customer_id", "updated_at"])
    op.execute("CREATE INDEX ix_memories_tsv ON customer_memories USING gin (tsv)")


def downgrade() -> None:
    op.drop_table("customer_memories")
