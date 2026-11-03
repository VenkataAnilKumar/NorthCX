"""Knowledge sources, documents and passages with full-text search.

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("stale_after_days", sa.Integer, nullable=True),
        sa.Column("created_at", sa.Float, nullable=False),
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("source_id", sa.String(200), sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("chunks", sa.Integer, nullable=False),
        sa.Column("source_updated_at", sa.Float, nullable=True),
        sa.Column("ingested_at", sa.Float, nullable=False),
        sa.UniqueConstraint("source_id", "external_id", name="uq_knowledge_doc"),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("document_id", sa.String(32), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("heading", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("search_text", sa.Text, nullable=False),
    )
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', search_text)) STORED")
    op.create_index("ix_knowledge_chunks_doc", "knowledge_chunks", ["document_id", "seq"])
    op.execute("CREATE INDEX ix_knowledge_chunks_tsv ON knowledge_chunks USING gin (tsv)")


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_sources")
