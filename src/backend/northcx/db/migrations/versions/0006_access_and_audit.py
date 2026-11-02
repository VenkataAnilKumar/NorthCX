"""API keys and the append-only audit log.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("key_id", sa.String(8), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(200), nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("expires_at", sa.Float, nullable=True),
        sa.Column("revoked_at", sa.Float, nullable=True),
        sa.Column("revoked_by", sa.String(200), nullable=True),
        sa.Column("last_used_at", sa.Float, nullable=True),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("at", sa.Float, nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("key_id", sa.String(16), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(300), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("detail", JSONB, nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_audit_actor", "audit_log", ["actor", "id"])
    op.create_index("ix_audit_action", "audit_log", ["action", "id"])
    # The log is append-only: refuse edits, deletes and truncation (the hash chain detects anything done around this).
    op.execute("""
        CREATE FUNCTION audit_log_immutable() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'audit_log is append-only'; END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log "
               "FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();")
    op.execute("CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
               "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_immutable();")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log")
    op.drop_table("audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_immutable()")
    op.drop_table("api_keys")
