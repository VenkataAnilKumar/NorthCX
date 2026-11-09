"""Tenant isolation, batch d: channels (email, SMS, voice, verification) (WP2.3 d). Provider and customer chosen ids are unique per tenant.

Revision ID: 0040
Revises: 0039
"""
import sqlalchemy as sa
from alembic import op

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

# table -> its old primary key column(s); the new key is tenant_id plus these
TABLES = {"email_sessions": ("session_id",), "email_messages": ("message_id",), "sms_sessions": ("session_id",), "sms_messages": ("message_id",),
          "sms_opt_outs": ("phone_hash",), "voice_calls": ("call_id",), "verification_codes": ("session_id",)}


def upgrade() -> None:
    for table, pk in TABLES.items():
        op.add_column(table, sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)))
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.create_primary_key(f"{table}_pkey", table, ["tenant_id", *pk])
        for sql in enable_rls_sql(table):
            op.execute(sql)


def downgrade() -> None:
    for table, pk in TABLES.items():
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"DELETE FROM {table} WHERE tenant_id <> 'default'")  # their ids may repeat the default tenant's
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.create_primary_key(f"{table}_pkey", table, list(pk))
        op.drop_column(table, "tenant_id")
