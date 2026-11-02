"""Database schema. Migrations in `migrations/versions` must match these models (a test checks it)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
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
    __table_args__ = (Index("ix_handoffs_state", "state", "created_at"), Index("ix_handoffs_session", "session_id"))


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
