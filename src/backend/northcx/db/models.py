"""Database schema. Migrations in `migrations/versions` must match these models (a test checks it)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Computed, DateTime, Float, ForeignKey, Identity, Index, Integer, LargeBinary, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageRow(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[Any] = mapped_column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_messages_session_seq"),)


class FactRow(Base):
    __tablename__ = "customer_facts"
    customer_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TraceRow(Base):
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


class TraceEventRow(Base):
    __tablename__ = "trace_events"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), ForeignKey("traces.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    t: Mapped[float] = mapped_column(Float, nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("trace_id", "seq", name="uq_trace_events_seq"),)


class ApprovalRow(Base):
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


class HandoffRow(Base):
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


class SimRunRow(Base):
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


class AgentVersionRow(Base):
    __tablename__ = "agent_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    spec: Mapped[Any] = mapped_column(JSONB, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (UniqueConstraint("agent_id", "number", name="uq_agent_versions_number"),)


class ReleaseRow(Base):
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
    __table_args__ = (Index("ix_audit_actor", "actor", "id"), Index("ix_audit_action", "action", "id"))


class OutboxRow(Base):
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


class EmailSessionRow(Base):
    __tablename__ = "email_sessions"
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    sender: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    verified: Mapped[bool] = mapped_column(nullable=False)
    last_message_id: Mapped[str] = mapped_column(String(998), nullable=False)
    references: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_email_sessions_sender", "sender"),)


class KnowledgeSourceRow(Base):
    __tablename__ = "knowledge_sources"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    stale_after_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class KnowledgeDocumentRow(Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    source_updated_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    ingested_at: Mapped[float] = mapped_column(Float, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_knowledge_doc"),)


class KnowledgeChunkRow(Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('english', search_text)", persisted=True))
    __table_args__ = (Index("ix_knowledge_chunks_doc", "document_id", "seq"), Index("ix_knowledge_chunks_tsv", "tsv", postgresql_using="gin"))


class VerificationCodeRow(Base):
    __tablename__ = "verification_codes"
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


class CrawlScheduleRow(Base):
    __tablename__ = "crawl_schedules"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(200), ForeignKey("knowledge_sources.id", ondelete="CASCADE"), nullable=False)
    config: Mapped[Any] = mapped_column(JSONB, nullable=False)
    every_hours: Mapped[float] = mapped_column(Float, nullable=False)
    next_run: Mapped[float] = mapped_column(Float, nullable=False)
    last_run: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_job_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_result: Mapped[str | None] = mapped_column(String(300), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_crawl_schedules_due", "enabled", "next_run"),)


class ManagedScenarioRow(Base):
    __tablename__ = "managed_scenarios"
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


class VoiceCallRow(Base):
    __tablename__ = "voice_calls"
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


class AttachmentRow(Base):
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


class SessionRouteRow(Base):
    __tablename__ = "session_routes"
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class RolloutRow(Base):
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
    __table_args__ = (Index("uq_rollouts_active", "agent_id", "environment", unique=True, postgresql_where=text("state = 'active'")),)


class RolloutAssignmentRow(Base):
    __tablename__ = "rollout_assignments"
    rollout_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    arm: Mapped[str] = mapped_column(String(16), nullable=False)
    __table_args__ = (Index("ix_rollout_assign_session", "session_id"),)


class ReviewRow(Base):
    __tablename__ = "conversation_reviews"
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    handoff: Mapped[str] = mapped_column(String(16), nullable=False)
    failures: Mapped[Any] = mapped_column(JSONB, nullable=False)
    note: Mapped[str] = mapped_column(String(1000), nullable=False, server_default="")
    reviewer: Mapped[str] = mapped_column(String(200), nullable=False)
    reviewed_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_reviews_at", "reviewed_at"),)


class ConversationTagRow(Base):
    __tablename__ = "conversation_tags"
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    tag: Mapped[str] = mapped_column(String(40), primary_key=True)
    by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_tags_tag", "tag"),)


class FeedbackRow(Base):
    __tablename__ = "conversation_feedback"
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(String(1000), nullable=False, server_default="")
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_feedback_created", "created_at"),)


class TraceExportRow(Base):
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


class InboxEventRow(Base):
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


class SmsSessionRow(Base):
    __tablename__ = "sms_sessions"
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    our_number: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    last_seen: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_sms_sessions_phone", "phone", "our_number", "last_seen"),)


class SmsMessageRow(Base):
    __tablename__ = "sms_messages"
    message_id: Mapped[str] = mapped_column(String(400), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    peer: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_sms_messages_session", "session_id"), Index("ix_sms_messages_peer", "peer", "direction", "created_at"))


class SmsOptOutRow(Base):
    """Opt-outs are kept by one-way hash of the number so a STOP is honoured even after the customer's data is erased."""
    __tablename__ = "sms_opt_outs"
    phone_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class CustomerMemoryRow(Base):
    __tablename__ = "customer_memories"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(200), nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_session: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))
    __table_args__ = (UniqueConstraint("customer_id", "text_hash", name="uq_memory_fact"), Index("ix_memories_customer", "customer_id", "updated_at"),
                      Index("ix_memories_tsv", "tsv", postgresql_using="gin"))


class SessionIndexRow(Base):
    """Which conversations belong to which customer ('' = no known customer), and when each was last active."""
    __tablename__ = "session_index"
    session_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    first_seen: Mapped[float] = mapped_column(Float, nullable=False)
    last_seen: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_session_index_customer", "customer_id"), Index("ix_session_index_seen", "last_seen"))


class IdempotencyRow(Base):
    __tablename__ = "idempotency_keys"
    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    req_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (Index("ix_idempotency_created", "created_at"), Index("ix_idempotency_session", "session_id"))


class MonitorFindingRow(Base):
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


class EmailMessageRow(Base):
    __tablename__ = "email_messages"
    message_id: Mapped[str] = mapped_column(String(998), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(200), nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    peer: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (Index("ix_email_messages_session", "session_id"), Index("ix_email_messages_peer", "peer", "direction", "created_at"))
