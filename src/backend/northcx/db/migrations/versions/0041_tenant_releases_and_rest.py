"""Tenant isolation, batches e and f: releases, versions, rollouts, scenarios, simulation runs, usage, groups, SCIM, idempotency, alerts, findings,
exports, qualifications and release requests (WP2.3 e and f). `api_keys`, `audit_log`, `tenants`, `channel_bindings`, `job_leases` and `rate_counters`
stay outside row-level security: a key must be found before its tenant is known, the audit chain runs across tenants, and the rest are platform data.

Revision ID: 0041
Revises: 0040
"""
import sqlalchemy as sa
from alembic import op

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL, enable_rls_sql

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

# table -> primary key columns after the change (None: unchanged)
TABLES = {
    "simulation_runs": None, "agent_versions": None, "releases": None, "rollouts": None, "rollout_assignments": None, "trace_exports": None,
    "model_qualifications": None, "groups": None, "scim_users": None, "release_requests": None, "alert_events": None, "monitor_findings": None,
    "managed_scenarios": ("tenant_id", "name"), "idempotency_keys": ("tenant_id", "scope"), "usage_ledger": ("tenant_id", "agent_id", "day"),
    "alert_state": ("tenant_id", "rule"),
}
OLD_PK = {"managed_scenarios": ("name",), "idempotency_keys": ("scope",), "usage_ledger": ("agent_id", "day"), "alert_state": ("rule",)}


def upgrade() -> None:
    op.drop_constraint("uq_agent_versions_number", "agent_versions", type_="unique")
    op.drop_constraint("groups_name_key", "groups", type_="unique")
    op.drop_constraint("groups_external_name_key", "groups", type_="unique")
    op.drop_constraint("scim_users_user_name_key", "scim_users", type_="unique")
    op.drop_index("uq_rollouts_active", table_name="rollouts")
    for table, pk in TABLES.items():
        op.add_column(table, sa.Column("tenant_id", sa.String(40), nullable=False, server_default=sa.text(TENANT_DEFAULT_SQL)))
        if pk:
            op.drop_constraint(f"{table}_pkey", table, type_="primary")
            op.create_primary_key(f"{table}_pkey", table, list(pk))
    op.create_unique_constraint("uq_agent_versions_number", "agent_versions", ["tenant_id", "agent_id", "number"])
    op.create_unique_constraint("groups_name_key", "groups", ["tenant_id", "name"])
    op.create_unique_constraint("groups_external_name_key", "groups", ["tenant_id", "external_name"])
    op.create_unique_constraint("scim_users_user_name_key", "scim_users", ["tenant_id", "user_name"])
    op.create_index("uq_rollouts_active", "rollouts", ["tenant_id", "agent_id", "environment"], unique=True, postgresql_where=sa.text("state = 'active'"))
    for table in TABLES:
        for sql in enable_rls_sql(table):
            op.execute(sql)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"DELETE FROM {table} WHERE tenant_id <> 'default'")  # their keys may repeat the default tenant's
    op.drop_index("uq_rollouts_active", table_name="rollouts")
    op.drop_constraint("scim_users_user_name_key", "scim_users", type_="unique")
    op.drop_constraint("groups_external_name_key", "groups", type_="unique")
    op.drop_constraint("groups_name_key", "groups", type_="unique")
    op.drop_constraint("uq_agent_versions_number", "agent_versions", type_="unique")
    for table, pk in OLD_PK.items():
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.create_primary_key(f"{table}_pkey", table, list(pk))
    for table in TABLES:
        op.drop_column(table, "tenant_id")
    op.create_index("uq_rollouts_active", "rollouts", ["agent_id", "environment"], unique=True, postgresql_where=sa.text("state = 'active'"))
    op.create_unique_constraint("scim_users_user_name_key", "scim_users", ["user_name"])
    op.create_unique_constraint("groups_external_name_key", "groups", ["external_name"])
    op.create_unique_constraint("groups_name_key", "groups", ["name"])
    op.create_unique_constraint("uq_agent_versions_number", "agent_versions", ["agent_id", "number"])
