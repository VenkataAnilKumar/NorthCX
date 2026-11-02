# NorthCX Feature Spec

Status: Draft. Detailed behaviour for feature groups in `NorthCX_Feature-Catalog.md`. "State" reflects the code today.

## 1. Agent definition (A1-A10)
- **Inputs:** `id`, `instructions` (goals, policies, tone), `tools`, `guardrails`, `model`, `maxSteps` (default 8).
- **Behaviour:** the instructions become the system prompt with the handoff rule and untrusted customer facts appended. An agent is plain data plus functions, so it is version-controlled.
- **Planned:** skills (named reusable procedures such as triage, respond, confirm) with a flexibility setting from strict steps to free-form; journeys (scenario blueprints with required steps and guardrails); templates; tone settings; generation of drafts from procedures or transcripts.
- **Acceptance:** an agent loads from a file, runs, and produces a trace. State: Built (core).

## 2. Runtime (R1-R10)
- **Loop:** model call, tool calls, guardrails, reply. Detailed in `04-ai-architecture/NorthCX_Agent-Runtime.md`.
- **Edge cases:** invalid tool input; unknown tool; tool exception; model failure; supervisor failure; step limit; rewrite limit; multiple tool calls in one turn including a handoff.
- **Guarantees:** saved history is valid and ends on an assistant turn; every exit path writes a trace.
- **Planned:** fallback model and retries; streaming; token and cost budget that escalates when exceeded; language detection and same-language replies; multi-agent routing; resume after approval.

## 3. Tools (T1-T8)
- **Definition:** name, description, typed input schema, `run`, optional `requiresApproval(input)`.
- **Behaviour:** schema validated first; guardrails second; approval third; execution last. Errors become tool results the model can react to.
- **Planned:** idempotency keys for writes; per-agent and per-customer permission scopes; secrets injected at run time; dry-run mode that records intended actions without executing; connector library for common business systems.
- **Acceptance:** an over-threshold call never executes without a recorded approval.

## 4. Supervision and safety (S1-S11)
- **Forced-handoff topics (built):** declared in the agent spec; a matching customer message escalates before the model runs.
- **Guardrail interface:** `checkToolCall`, `checkReply`; allow/deny with reason.
- **Built:** card-number rule (with validity check), model-based policy supervisor, fail-closed handling, untrusted facts.
- **Planned:** input checks for tool output; PII detection and redaction; coverage of every conversation by monitoring; a policy library with its own tests.
- **Acceptance:** each policy has at least one passing and one blocking scenario.

## 5. Handoff and approvals (H1-H8)
Specified in `NorthCX_Handoff-and-Approvals-Spec.md`.

## 6. Channels (C1-C10)
- **Contract:** adapter maps a channel message to the chat API and posts the reply; session ID stable per conversation; escalation routes to the inbox.
- **Built:** HTTP API and widget.
- **Planned:** email (thread to session), SMS and messaging, voice, mobile/web SDK, attachments, per-channel style and identity verification.
- **Acceptance:** each channel passes a round-trip scenario including handoff.

## 7. Knowledge and memory (K1-K8)
- **Memory:** session history and customer facts behind `MemoryStore`.
- **Knowledge:** a retrieval tool returns passages with source references; the agent must not assert beyond them; freshness metadata on sources.
- **Context at start:** optional pull of customer data from business systems.
- **Lifecycle:** retention, export, deletion per customer; summarisation of long histories.

## 8. Testing and release (Q1-Q12)
- **Simulations:** scenarios with scripted or simulated customers, assertions, optional judge. See `04-ai-architecture/NorthCX_Simulation-and-Evals.md`.
- **Release:** `NorthCX_Release-Management.md`.

## 9. Observability and insights (O1-O10)
- **Built:** trace per run, trace API.
- **Planned:** OpenTelemetry export, redaction, metrics, containment and satisfaction, intent gaps, failure analysis, alerts, conversation search and tags, natural-language analytics.

## 10. Studio (U1-U8)
Screens and behaviour in `07-design/NorthCX_Studio-UI-Spec.md`.

## 11. Platform (P1-P11)
- **Built:** bearer key auth, environment configuration.
- **Planned:** roles and scoped keys, audit log, rate limiting, single sign-on, containers, webhooks, data-residency options; later, multi-tenancy and usage metering.
