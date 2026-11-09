"""A money column on the usage ledger, for budgets in currency.

Revision ID: 0031
Revises: 0030
"""
import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_ledger", sa.Column("cost_micros", sa.BigInteger, nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("usage_ledger", "cost_micros")
