"""Tenant isolation, batch b: conversation data (WP2.3 b, WP2.4 for these tables).

Adds `tenant_id` (default from the session's tenant, existing rows are 'default'), makes client-chosen ids unique per tenant, and turns on
row-level security with one policy per table. The application's database role must not be the table owner or a superuser for the policies to
apply (the server checks this when tenancy is in use).

Revision ID: 0038
Revises: 0037
"""
import sqlalchemy as sa
from alembic import op

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

# table -> new primary key (None: the primary key stays as it is)
TABLES: dict[str, tuple[str, ...] | None] = {
    "sessions": ("tenant_id", "id"),
    "messages": None,
    "customer_facts": ("tenant_id", "customer_id", "key"),
    "traces": None,
    "trace_events": None,
    "approvals": None,
    "handoffs": None,
    "outbox": None,
    "inbox_events": None,
    "session_routes": ("tenant_id", "session_id"),
    "session_index": ("tenant_id", "session_id", "customer_id"),
    "customer_memories": None,
    "conversation_feedback": ("tenant_id", "session_id"),
    "conversation_tags": ("tenant_id", "session_id", "tag"),
    "conversation_reviews": ("tenant_id", "session_id"),
}


def upgrade() -> None:
    op.drop_constraint("messages_session_id_fkey", "messages", type_="foreignkey")
    op.drop_constraint("uq_messages_session_seq", "messages", type_="unique")
    op.drop_constraint("uq_memory_fact", "customer_memories", type_="unique")
    for table, pk in TABLES.items():
        op.add_column(table, sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)))
        if pk:
            op.drop_constraint(f"{table}_pkey", table, type_="primary")
            op.create_primary_key(f"{table}_pkey", table, list(pk))
    op.create_unique_constraint("uq_messages_session_seq", "messages", ["tenant_id", "session_id", "seq"])
    op.create_foreign_key("messages_tenant_id_session_id_fkey", "messages", "sessions", ["tenant_id", "session_id"], ["tenant_id", "id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_memory_fact", "customer_memories", ["tenant_id", "customer_id", "text_hash"])
    for table in TABLES:
        for sql in enable_rls_sql(table):
            op.execute(sql)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_constraint("uq_memory_fact", "customer_memories", type_="unique")
    op.drop_constraint("messages_tenant_id_session_id_fkey", "messages", type_="foreignkey")
    op.drop_constraint("uq_messages_session_seq", "messages", type_="unique")
    old_pk = {"sessions": ("id",), "customer_facts": ("customer_id", "key"), "session_routes": ("session_id",), "session_index": ("session_id", "customer_id"),
              "conversation_feedback": ("session_id",), "conversation_tags": ("session_id", "tag"), "conversation_reviews": ("session_id",)}
    for table, pk in old_pk.items():
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.create_primary_key(f"{table}_pkey", table, list(pk))
    for table in TABLES:
        op.drop_column(table, "tenant_id")
    op.create_unique_constraint("uq_memory_fact", "customer_memories", ["customer_id", "text_hash"])
    op.create_unique_constraint("uq_messages_session_seq", "messages", ["session_id", "seq"])
    op.create_foreign_key("messages_session_id_fkey", "messages", "sessions", ["session_id"], ["id"], ondelete="CASCADE")
