"""Session index for export, erasure and retention; idempotent replies know their conversation.

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_index",
        sa.Column("session_id", sa.String(200), primary_key=True),
        sa.Column("customer_id", sa.String(200), primary_key=True),
        sa.Column("first_seen", sa.Float, nullable=False),
        sa.Column("last_seen", sa.Float, nullable=False),
    )
    op.create_index("ix_session_index_customer", "session_index", ["customer_id"])
    op.create_index("ix_session_index_seen", "session_index", ["last_seen"])
    # Conversations that existed before this migration are indexed as having no known customer, aged by their last update.
    op.execute("INSERT INTO session_index (session_id, customer_id, first_seen, last_seen) "
               "SELECT id, '', extract(epoch FROM created_at), extract(epoch FROM updated_at) FROM sessions")
    op.add_column("idempotency_keys", sa.Column("session_id", sa.String(200), nullable=True))
    op.create_index("ix_idempotency_session", "idempotency_keys", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_session", table_name="idempotency_keys")
    op.drop_column("idempotency_keys", "session_id")
    op.drop_table("session_index")
