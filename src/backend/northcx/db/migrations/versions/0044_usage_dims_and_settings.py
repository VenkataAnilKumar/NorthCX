"""Usage by model and by team, per-tenant settings changed from the Admin app, and the groups a sign-in session was given.

Revision ID: 0044
Revises: 0043
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("groups", JSONB, nullable=True))
    op.create_table(
        "usage_dims",
        sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("tokens", sa.BigInteger, nullable=False),
        sa.Column("cost_micros", sa.BigInteger, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("tenant_id", "day", "kind", "key", name="usage_dims_pkey"),
    )
    op.create_table(
        "tenant_settings",
        sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("updated_by", sa.String(200), nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "key", name="tenant_settings_pkey"),
    )
    for table in ("usage_dims", "tenant_settings"):
        for sql in enable_rls_sql(table):
            op.execute(sql)


def downgrade() -> None:
    op.drop_table("tenant_settings")
    op.drop_table("usage_dims")
    op.drop_column("api_keys", "groups")
