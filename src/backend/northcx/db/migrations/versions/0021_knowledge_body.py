"""Keep the submitted text of knowledge documents so they can be edited.

Revision ID: 0021
Revises: 0020
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("body", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_documents", "body")
