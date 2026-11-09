"""Model verdicts on conversations (Quality), tenant-isolated from the start.

Revision ID: 0051
Revises: 0050
"""
import sqlalchemy as sa
from alembic import op

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("qa_judgements", sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)), sa.Column("session_id", sa.String(200), nullable=False),
                    sa.Column("verdict", sa.String(8), nullable=False), sa.Column("reason", sa.String(400), nullable=False), sa.Column("rubric_version", sa.Integer, nullable=False),
                    sa.Column("judged_by", sa.String(200), nullable=False), sa.Column("created_at", sa.Float, nullable=False), sa.PrimaryKeyConstraint("tenant_id", "session_id", name="qa_judgements_pkey"))
    for sql in enable_rls_sql("qa_judgements"):
        op.execute(sql)


def downgrade() -> None:
    op.drop_table("qa_judgements")
