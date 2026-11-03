"""Hand-off queues and after-hours flag.

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("handoffs", sa.Column("queue", sa.String(64), nullable=True))
    op.add_column("handoffs", sa.Column("after_hours", sa.Boolean, nullable=False, server_default="false"))
    op.create_index("ix_handoffs_queue", "handoffs", ["queue", "state"])


def downgrade() -> None:
    op.drop_index("ix_handoffs_queue", table_name="handoffs")
    op.drop_column("handoffs", "after_hours")
    op.drop_column("handoffs", "queue")
