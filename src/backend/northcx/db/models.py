"""Database schema. Migrations in `migrations/versions` must match these models (a test checks it)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Computed, DateTime, Float, ForeignKey, ForeignKeyConstraint, Identity, Index, Integer, LargeBinary, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR

from northcx.db.tenant_sql import TENANT_DEFAULT_SQL
from northcx.tenancy import current_tenant
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def tenant_col(pk: bool = False) -> Any:
    """The tenant a row belongs to: filled from the session's tenant by the database (and by the ORM), isolated by row-level security."""
    return mapped_column(String(40), primary_key=pk, nullable=False, server_default=text(TENANT_DEFAULT_SQL), default=current_tenant)


class TenantScoped:
    """Marks the models whose rows belong to one tenant (the ORM adds the tenant predicate to their statements)."""
    tenant_id: Mapped[str] = tenant_col()


class SessionRow(TenantScoped, Base):
    __tablename__ = "sessions"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageRow(TenantScoped, Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[Any] = mapped_column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "session_id", "seq", name="uq_messages_session_seq"),
                      ForeignKeyConstraint(["tenant_id", "session_id"], ["sessions.tenant_id", "sessions.id"], ondelete="CASCADE"))


class FactRow(TenantScoped, Base):
    __tablename__ = "customer_facts"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    customer_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TraceRow(TenantScoped, Base):
    __tablename__ = "traces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    tools: Mapped[Any] = mapped_column(JSONB, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False, server_default="production")
    __table_args__ = (Index("ix_traces_session", "session_id"), Index("ix_traces_started", "started_at"))


class TraceEventRow(TenantScoped, Base):
    __tablename__ = "trace_events"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), ForeignKey("traces.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    t: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("trace_id", "seq", name="uq_trace_events_seq"),)


class ApprovalRow(TenantScoped, Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    tool: Mapped[str] = mapped_column(String(200), nullable=False)
    input: Mapped[Any] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decided_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    customer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[Any] = mapped_column(JSONB, nullable=True)
    __table_args__ = (Index("ix_approvals_state", "state"),)


class HandoffRow(TenantScoped, Base):
    __tablename__ = "handoffs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    topics: Mapped[Any] = mapped_column(JSONB, nullable=False)
    package: Mapped[Any] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolved_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    queue: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hours: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    __table_args__ = (Index("ix_handoffs_state", "state", "created_at"), Index("ix_handoffs_session", "session_id"), Index("ix_handoffs_queue", "queue", "state"))


class SimRunRow(TenantScoped, Base):
    __tablename__ = "simulation_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False)
    seconds: Mapped[float] = mapped_column(Float, nullable=False)
    counts: Mapped[Any] = mapped_column(JSONB, nullable=False)
    agent_digests: Mapped[Any] = mapped_column(JSONB, nullable=False)
    meta: Mapped[Any] = mapped_column(JSONB, nullable=False)
    results: Mapped[Any] = mapped_column(JSONB, nullable=False)
    __table_args__ = (Index("ix_simulation_runs_created", "created_at"),)


class AgentVersionRow(TenantScoped, Base):
    __tablename__ = "agent_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    spec: Mapped[Any] = mapped_column(JSONB, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "agent_id", "number", name="uq_agent_versions_number"),)


class ReleaseRow(TenantScoped, Base):
    __tablename__ = "releases"
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    version_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("agent_versions.id"), nullable=True)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    by: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_releases_agent_env", "agent_id", "environment", "seq"),)


class ApiKeyRow(Base):
    __tablename__ = "api_keys"
    key_id: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    revoked_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_used_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(40), nullable=False, server_default="default", index=True)
    extra_roles: Mapped[Any] = mapped_column(JSONB, nullable=True)  # roles added by group membership at sign-in
    groups: Mapped[Any] = mapped_column(JSONB, nullable=True)  # names of the groups the person was in at sign-in (their teams, for usage)
    agents: Mapped[Any] = mapped_column(JSONB, nullable=True)  # null: all agents
    environments: Mapped[Any] = mapped_column(JSONB, nullable=True)  # null: all environments


class AuditRow(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    at: Mapped[float] = mapped_column(Float, nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    key_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(300), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[Any] = mapped_column(JSONB, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(40), nullable=False, server_default="default")
    __table_args__ = (Index("ix_audit_actor", "actor", "id"), Index("ix_audit_action", "action", "id"), Index("ix_audit_tenant", "tenant_id", "id"))


class OutboxRow(TenantScoped, Base):
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    delivered_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_attempt_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (Index("ix_outbox_session", "session_id", "id"),)


class EmailSessionRow(TenantScoped, Base):
    __tablename__ = "email_sessions"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    sender: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    verified: Mapped[bool] = mapped_column(nullable=False)
    last_message_id: Mapped[str] = mapped_column(String(998), nullable=False)
    references: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_email_sessions_sender", "sender"),)


class KnowledgeSourceRow(TenantScoped, Base):
    __tablename__ = "knowledge_sources"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    stale_after_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class KnowledgeDocumentRow(TenantScoped, Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    source_updated_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    ingested_at: Mapped[float] = mapped_column(Float, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "source_id", "external_id", name="uq_knowledge_doc"),
                      ForeignKeyConstraint(["tenant_id", "source_id"], ["knowledge_sources.tenant_id", "knowledge_sources.id"], ondelete="CASCADE"))


class KnowledgeChunkRow(TenantScoped, Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('english', search_text)", persisted=True))
    __table_args__ = (Index("ix_knowledge_chunks_doc", "document_id", "seq"), Index("ix_knowledge_chunks_tsv", "tsv", postgresql_using="gin"))


class VerificationCodeRow(TenantScoped, Base):
    __tablename__ = "verification_codes"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[str] = mapped_column(String(10), nullable=False)
    dest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    sends: Mapped[Any] = mapped_column(JSONB, nullable=False)
    verified_until: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class CrawlScheduleRow(TenantScoped, Base):
    __tablename__ = "crawl_schedules"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    config: Mapped[Any] = mapped_column(JSONB, nullable=False)
    every_hours: Mapped[float] = mapped_column(Float, nullable=False)
    next_run: Mapped[float] = mapped_column(Float, nullable=False)
    last_run: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_job_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_result: Mapped[str | None] = mapped_column(String(300), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_crawl_schedules_due", "enabled", "next_run"),
                      ForeignKeyConstraint(["tenant_id", "source_id"], ["knowledge_sources.tenant_id", "knowledge_sources.id"], ondelete="CASCADE"))


class ManagedScenarioRow(TenantScoped, Base):
    __tablename__ = "managed_scenarios"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    required: Mapped[bool] = mapped_column(nullable=False)
    definition: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (Index("ix_managed_scenarios_agent", "agent_id"),)


class VoiceCallRow(TenantScoped, Base):
    __tablename__ = "voice_calls"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    call_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    caller_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[float] = mapped_column(Float, nullable=False)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    consent: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded: Mapped[bool] = mapped_column(nullable=False)
    turns: Mapped[int] = mapped_column(Integer, nullable=False)
    barge_ins: Mapped[int] = mapped_column(Integer, nullable=False)
    languages: Mapped[Any] = mapped_column(JSONB, nullable=False)
    handoff_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[Any] = mapped_column(JSONB, nullable=False)
    __table_args__ = (Index("ix_voice_calls_started", "started_at"), Index("ix_voice_calls_session", "session_id"))


class AttachmentRow(TenantScoped, Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    media_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_attachments_session", "session_id"),)


class SessionRouteRow(TenantScoped, Base):
    __tablename__ = "session_routes"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class RolloutRow(TenantScoped, Base):
    __tablename__ = "rollouts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    candidate_number: Mapped[int] = mapped_column(Integer, nullable=False)
    control_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percent: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    started_by: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ended_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[float] = mapped_column(Float, nullable=False)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (Index("uq_rollouts_active", "tenant_id", "agent_id", "environment", unique=True, postgresql_where=text("state = 'active'")),)


class RolloutAssignmentRow(TenantScoped, Base):
    __tablename__ = "rollout_assignments"
    rollout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    arm: Mapped[str] = mapped_column(String(16), nullable=False)
    __table_args__ = (Index("ix_rollout_assign_session", "session_id"),)


class ReviewRow(TenantScoped, Base):
    __tablename__ = "conversation_reviews"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    handoff: Mapped[str] = mapped_column(String(16), nullable=False)
    failures: Mapped[Any] = mapped_column(JSONB, nullable=False)
    note: Mapped[str] = mapped_column(String(1000), nullable=False, server_default="")
    reviewer: Mapped[str] = mapped_column(String(200), nullable=False)
    reviewed_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_reviews_at", "reviewed_at"),)


class ConversationTagRow(TenantScoped, Base):
    __tablename__ = "conversation_tags"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    tag: Mapped[str] = mapped_column(String(40), primary_key=True)
    by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_tags_tag", "tag"),)


class FeedbackRow(TenantScoped, Base):
    __tablename__ = "conversation_feedback"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(String(1000), nullable=False, server_default="")
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_feedback_created", "created_at"),)


class TraceExportRow(TenantScoped, Base):
    __tablename__ = "trace_exports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exporter: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_attempt_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivered_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    __table_args__ = (Index("ix_trace_exports_trace", "trace_id"), Index("ix_trace_exports_pending", "delivered_at", "created_at"))


class InboxEventRow(TenantScoped, Base):
    __tablename__ = "inbox_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    handoff_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connector: Mapped[str] = mapped_column(String(32), nullable=False)
    event: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_attempt_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivered_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    __table_args__ = (Index("ix_inbox_events_handoff", "handoff_id"), Index("ix_inbox_events_pending", "delivered_at", "created_at"))


class SmsSessionRow(TenantScoped, Base):
    __tablename__ = "sms_sessions"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    our_number: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    last_seen: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_sms_sessions_phone", "phone", "our_number", "last_seen"),)


class SmsMessageRow(TenantScoped, Base):
    __tablename__ = "sms_messages"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    message_id: Mapped[str] = mapped_column(String(400), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    peer: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_sms_messages_session", "session_id"), Index("ix_sms_messages_peer", "peer", "direction", "created_at"))


class SmsOptOutRow(TenantScoped, Base):
    """Opt-outs are kept by one-way hash of the number so a STOP is honoured even after the customer's data is erased."""
    __tablename__ = "sms_opt_outs"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    phone_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class CustomerMemoryRow(TenantScoped, Base):
    __tablename__ = "customer_memories"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(200), nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_session: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))
    __table_args__ = (UniqueConstraint("tenant_id", "customer_id", "text_hash", name="uq_memory_fact"), Index("ix_memories_customer", "customer_id", "updated_at"),
                      Index("ix_memories_tsv", "tsv", postgresql_using="gin"))


class SessionIndexRow(TenantScoped, Base):
    """Which conversations belong to which customer ('' = no known customer), and when each was last active."""
    __tablename__ = "session_index"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    first_seen: Mapped[float] = mapped_column(Float, nullable=False)
    last_seen: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_session_index_customer", "customer_id"), Index("ix_session_index_seen", "last_seen"))


class IdempotencyRow(TenantScoped, Base):
    __tablename__ = "idempotency_keys"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    req_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (Index("ix_idempotency_created", "created_at"), Index("ix_idempotency_session", "session_id"))


class RateCounterRow(Base):
    """Requests counted per key per fixed time window, shared by every server process. Old windows are deleted."""
    __tablename__ = "rate_counters"
    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    window_start: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # epoch seconds of the window's start (database clock)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class UsageLedgerRow(TenantScoped, Base):
    """Model tokens used per agent per UTC day, shared by every server process."""
    __tablename__ = "usage_ledger"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    agent_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")  # money in millionths of the budget currency


class ModelQualificationRow(TenantScoped, Base):
    """The result of qualifying one model for one agent definition, from a stored live simulation run."""
    __tablename__ = "model_qualifications"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    result: Mapped[Any] = mapped_column(JSONB, nullable=False)


class GroupRow(TenantScoped, Base):
    """A group: roles bound to a set of people (hand-added subjects and/or an identity provider group name)."""
    __tablename__ = "groups"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    external_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")
    roles: Mapped[Any] = mapped_column(JSONB, nullable=False)
    members: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="groups_name_key"), UniqueConstraint("tenant_id", "external_name", name="groups_external_name_key"))


class ScimUserRow(TenantScoped, Base):
    """A person provisioned by SCIM: whether they may sign in (WP3.3)."""
    __tablename__ = "scim_users"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    user_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "user_name", name="scim_users_user_name_key"),)


class ReleaseRequestRow(TenantScoped, Base):
    """A publish or promote waiting for a second person (WP3.5)."""
    __tablename__ = "release_requests"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    decided_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class TenantRow(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class ChannelBindingRow(Base):
    """An inbound address (phone number id, bot id, SMS number, email domain, voice number) belongs to exactly one tenant."""
    __tablename__ = "channel_bindings"
    kind: Mapped[str] = mapped_column(String(24), primary_key=True)
    address: Mapped[str] = mapped_column(String(200), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class WorkspaceTaskRow(TenantScoped, Base):
    """A Pilot task: questions, plan, steps and versioned results (E6)."""
    __tablename__ = "workspace_tasks"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    owner: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)
    __table_args__ = (Index("ix_workspace_tasks_owner", "tenant_id", "owner", "created_at"),)


class TemplateInstallRow(TenantScoped, Base):
    """Which hub template an agent was installed from, with the settings used and the agent as the template made it (E22)."""
    __tablename__ = "template_installs"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    agent_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)
    installed_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class UsageDimRow(TenantScoped, Base):
    """Usage by model and by team, per UTC day (tokens and money in millionths of the budget currency)."""
    __tablename__ = "usage_dims"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), primary_key=True)   # model | team
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class TenantSettingRow(TenantScoped, Base):
    """A setting an administrator changes from the Admin app, overriding the environment default for that tenant."""
    __tablename__ = "tenant_settings"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(200), nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class OrgPolicyRow(TenantScoped, Base):
    """One version of an organization policy (E16): draft, proposed, active, rejected, retired or superseded."""
    __tablename__ = "org_policies"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)


class OrgTemplateRow(TenantScoped, Base):
    """One version of an organization's own Hub template (WP22.5): draft, proposed, published, rejected, superseded or withdrawn."""
    __tablename__ = "org_templates"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)


class CoachingNoteRow(TenantScoped, Base):
    """A coaching note a lead or reviewer wrote about a conversation (E7)."""
    __tablename__ = "coaching_notes"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    about: Mapped[str] = mapped_column(String(80), nullable=False)
    note: Mapped[str] = mapped_column(String(1000), nullable=False)
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class CustomerNoteRow(TenantScoped, Base):
    """A staff note about a customer (Customers tab)."""
    __tablename__ = "customer_notes"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    note: Mapped[str] = mapped_column(String(1000), nullable=False)
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class AutomationRow(TenantScoped, Base):
    """One version of a routine (E8): draft, proposed, published, rejected, superseded or retired."""
    __tablename__ = "automations"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)


class AutomationRunRow(TenantScoped, Base):
    """One run of a routine, with each step's result."""
    __tablename__ = "automation_runs"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    automation_id: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)
    __table_args__ = (Index("ix_automation_runs_auto", "automation_id", "started_at"),)


class AutomationStateRow(TenantScoped, Base):
    """When a scheduled routine runs next, and whether it is paused."""
    __tablename__ = "automation_state"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    automation_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    next_run: Mapped[float | None] = mapped_column(Float, nullable=True)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class WorkspaceOutputRow(TenantScoped, Base):
    """A result a person kept in the Workspace (Outputs), with its versions."""
    __tablename__ = "workspace_outputs"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    visibility: Mapped[str] = mapped_column(String(10), nullable=False)
    space_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)
    __table_args__ = (Index("ix_workspace_outputs_space", "space_id"), Index("ix_workspace_outputs_owner", "owner"), Index("ix_workspace_outputs_expires", "expires_at"))


class WorkspaceSpaceRow(TenantScoped, Base):
    """A space: instructions and a home for outputs."""
    __tablename__ = "workspace_spaces"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    visibility: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)


class QaJudgementRow(TenantScoped, Base):
    """A model's verdict on a conversation (Quality); a person's review is separate and decides."""
    __tablename__ = "qa_judgements"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    verdict: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str] = mapped_column(String(400), nullable=False)
    rubric_version: Mapped[int] = mapped_column(Integer, nullable=False)
    judged_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class JobLeaseRow(Base):
    """Which server process currently runs a named background job (see northcx/leases.py)."""
    __tablename__ = "job_leases"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    holder: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False)  # epoch seconds on the database clock


class AlertStateRow(TenantScoped, Base):
    """An alert that is firing right now, so whichever server evaluates the rules next knows not to fire it again."""
    __tablename__ = "alert_state"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    rule: Mapped[str] = mapped_column(String(100), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class AlertEventRow(TenantScoped, Base):
    """Recent alert events (fired, cleared, test) with their delivery status, visible from any server."""
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    at: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class CrawlJobRow(TenantScoped, Base):
    """A website crawl and how far it has got, visible from any server. `updated_at` is its heartbeat."""
    __tablename__ = "crawl_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    __table_args__ = (Index("ix_crawl_jobs_source_state", "source_id", "state"), Index("ix_crawl_jobs_started", "started_at"))


class MonitorFindingRow(TenantScoped, Base):
    __tablename__ = "monitor_findings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    rule: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[str] = mapped_column(String(400), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_monitor_created", "created_at"), Index("ix_monitor_rule", "rule", "created_at"), Index("ix_monitor_session", "session_id"))


class EmailMessageRow(TenantScoped, Base):
    __tablename__ = "email_messages"
    tenant_id: Mapped[str] = tenant_col(pk=True)
    message_id: Mapped[str] = mapped_column(String(998), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    peer: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_email_messages_session", "session_id"), Index("ix_email_messages_peer", "peer", "direction", "created_at"))
