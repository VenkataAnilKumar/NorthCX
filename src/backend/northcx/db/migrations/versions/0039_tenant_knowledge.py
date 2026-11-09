"""Tenant isolation, batch c: knowledge, crawling and attachments (WP2.3 c). Same method as batch b (0038).

Revision ID: 0039
Revises: 0038
"""
import sqlalchemy as sa
from alembic import op

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

TABLES = ["knowledge_sources", "knowledge_documents", "knowledge_chunks", "crawl_schedules", "crawl_jobs", "attachments"]


def upgrade() -> None:
    op.drop_constraint("knowledge_documents_source_id_fkey", "knowledge_documents", type_="foreignkey")
    op.drop_constraint("crawl_schedules_source_id_fkey", "crawl_schedules", type_="foreignkey")
    op.drop_constraint("uq_knowledge_doc", "knowledge_documents", type_="unique")
    for table in TABLES:
        op.add_column(table, sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)))
    op.drop_constraint("knowledge_sources_pkey", "knowledge_sources", type_="primary")
    op.create_primary_key("knowledge_sources_pkey", "knowledge_sources", ["tenant_id", "id"])
    op.create_unique_constraint("uq_knowledge_doc", "knowledge_documents", ["tenant_id", "source_id", "external_id"])
    op.create_foreign_key("knowledge_documents_tenant_id_source_id_fkey", "knowledge_documents", "knowledge_sources", ["tenant_id", "source_id"], ["tenant_id", "id"], ondelete="CASCADE")
    op.create_foreign_key("crawl_schedules_tenant_id_source_id_fkey", "crawl_schedules", "knowledge_sources", ["tenant_id", "source_id"], ["tenant_id", "id"], ondelete="CASCADE")
    for table in TABLES:
        for sql in enable_rls_sql(table):
            op.execute(sql)


def downgrade() -> None:
    # Going back to a schema with one tenant cannot keep the other tenants' rows (their ids may repeat), so they are removed.
    for table in reversed(list(TABLES)):
        op.execute(f"DELETE FROM {table} WHERE tenant_id <> 'default'")
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_constraint("crawl_schedules_tenant_id_source_id_fkey", "crawl_schedules", type_="foreignkey")
    op.drop_constraint("knowledge_documents_tenant_id_source_id_fkey", "knowledge_documents", type_="foreignkey")
    op.drop_constraint("uq_knowledge_doc", "knowledge_documents", type_="unique")
    op.drop_constraint("knowledge_sources_pkey", "knowledge_sources", type_="primary")
    op.create_primary_key("knowledge_sources_pkey", "knowledge_sources", ["id"])
    for table in TABLES:
        op.drop_column(table, "tenant_id")
    op.create_unique_constraint("uq_knowledge_doc", "knowledge_documents", ["source_id", "external_id"])
    op.create_foreign_key("crawl_schedules_source_id_fkey", "crawl_schedules", "knowledge_sources", ["source_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("knowledge_documents_source_id_fkey", "knowledge_documents", "knowledge_sources", ["source_id"], ["id"], ondelete="CASCADE")
