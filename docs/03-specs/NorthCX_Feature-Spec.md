# NorthCX Feature Spec

Status: **Built**. Updated: 2026-11-09. Master for: detailed behaviour of the 1.0 feature groups. Detailed behaviour for feature groups in `NorthCX_Feature-Catalog.md`. "State" reflects the code today.

## 1. Agent definition (A1-A10)
- **Inputs:** `id`, `instructions` (goals, policies, tone), `tools`, `guardrails`, `model`, `max_steps` (default 8) (`northcx/agent.py`; YAML specs in `northcx/spec.py`).
- **Behaviour:** the instructions become the system prompt with the handoff rule and untrusted customer facts appended. An agent is plain data plus functions, so it is version-controlled.
- **Built:** skills (named reusable procedures such as triage, respond, confirm) with a flexibility setting from strict steps (enforced) to free-form; journeys (scenario blueprints with required steps, rules and hand-off conditions); templates; tone settings and forbidden phrases; drafts from plain-language descriptions, procedures, transcripts and (with a transcription service) recordings. Never saved without a person.
- **Acceptance:** an agent loads from a file, runs, and produces a trace. State: Built.

## 2. Runtime (R1-R10)
- **Loop:** model call, tool calls, guardrails, reply. Detailed in `04-ai-architecture/NorthCX_Agent-Runtime.md`.
- **Edge cases:** invalid tool input; unknown tool; tool exception; model failure; supervisor failure; step limit; rewrite limit; multiple tool calls in one turn including a handoff.
- **Guarantees:** saved history is valid and ends on an assistant turn; every exit path writes a trace.
- **Built:** fallback model and retries; progressive delivery of the checked reply with tool progress; token budgets per turn and per day that escalate when exceeded; offline language detection and same-language replies; specialist agents and transfers; resume after approval. **Planned:** budgets in currency and cheaper-model routing (E1).

## 3. Tools (T1-T8)
- **Definition:** `Tool` (`northcx/agent.py`): name, description, a Pydantic input model, `run`, optional `requires_approval(input)` returning a reason, and `effect` (`read` or `write`, default `write`).
- **Behaviour:** schema validated first; guardrails second; approval third; execution last. Errors become tool results the model can react to.
- **Built:** idempotency keys for writes; per-agent and per-customer permission scopes (customer, facts, channel); secrets injected at run time and scrubbed from everything stored; dry-run mode that records intended actions without executing; connector library of generic YAML starting points with pagination and OAuth 2. **Planned:** native vendor connectors and an MCP client (E4, E9).
- **Acceptance:** an over-threshold call never executes without a recorded approval.

## 4. Supervision and safety (S1-S11)
- **Forced-handoff topics (built):** declared in the agent spec; a matching customer message escalates before the model runs.
- **Guardrail interface:** `check_tool_call` and `check_reply` return a `Verdict` (allowed, or denied with a reason) (`northcx/guardrails.py`).
- **Built:** card-number rule (with validity check), model-based policy supervisor, fail-closed handling, untrusted facts.
- **Built:** input checks on customer messages and on tool output; PII detection and masking; always-on monitoring of every turn; a policy library with its own allow and block cases; abuse and flood detection; identity verification by one-time code.
- **Acceptance:** each policy has at least one passing and one blocking scenario.

## 5. Handoff and approvals (H1-H8)
Specified in `NorthCX_Handoff-and-Approvals-Spec.md`.

## 6. Channels (C1-C10)
- **Contract:** adapter maps a channel message to the chat API and posts the reply; session ID stable per conversation; escalation routes to the inbox.
- **Built:** HTTP API, web widget and browser SDK.
- **Built:** email (thread to session), SMS (Twilio-compatible), WhatsApp (several numbers, pictures and documents in, approved templates out), Telegram, voice (provider-neutral bridge with consent, barge-in and keypad), attachments, per-channel style and identity verification. **Planned:** other messaging apps, sending media and buttons, native mobile SDKs.
- **Acceptance:** each channel passes a round-trip scenario including handoff.

## 7. Knowledge and memory (K1-K8)
- **Memory:** session history and customer facts behind `MemoryStore` (in memory or Postgres); long-term memories through `MemoryService`. See `04-ai-architecture/NorthCX_Knowledge-and-Memory.md`.
- **Knowledge:** the `search_knowledge` tool returns passages with numbered source references (see `05-technical/NorthCX_Knowledge-Design.md`); the agent must not assert beyond them; freshness metadata on sources.
- **Context at start:** optional pull of customer data from business systems.
- **Lifecycle:** retention, export, deletion per customer; summarisation of long histories.

## 8. Testing and release (Q1-Q12)
- **Simulations:** scenarios with scripted or simulated customers, assertions, optional judge. See `04-ai-architecture/NorthCX_Simulation-and-Evals.md`.
- **Release:** `NorthCX_Release-Management.md`.

## 9. Observability and insights (O1-O10)
- **Built:** trace per run and trace API; trace export (OpenTelemetry, Langfuse) with redaction; metrics with denominators, containment and satisfaction, intent gaps, failure analysis; alerts with delivery tracking; conversation search and tags; plain-language analytics with filters and charts; signed status events.

## 10. Studio (U1-U8)
Screens and behaviour in `07-design/NorthCX_Studio.md`.

## 11. Platform (P1-P11)
- **Built:** bearer key auth, environment and file configuration; seven roles with hashed, expiring keys; hash-chained audit log; rate limits; OpenID Connect single sign-on; containers and a compose stack; signed webhooks and status events; data-residency policy; self-hosting.
- **Built since 1.0 work began:** shared rate limits and budgets across processes (Postgres backend), several processes with roles and job leases.
- **Planned:** keys scoped to particular agents, SAML and SCIM, multi-tenancy and usage metering (see `08-implementation/NorthCX_Implementation-Plan.md`, epics E2, E3, E10).
