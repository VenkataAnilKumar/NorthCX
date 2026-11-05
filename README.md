<div align="center">

<img src="docs/assets/banner.svg" alt="NorthCX: supervised AI agents that resolve customer issues, end to end" width="100%">

<br>

[![CI](https://github.com/VenkataAnilKumar/NorthCX/actions/workflows/ci.yml/badge.svg)](https://github.com/VenkataAnilKumar/NorthCX/actions/workflows/ci.yml)
[![Licence: Apache-2.0](https://img.shields.io/badge/licence-Apache--2.0-1747b8)](LICENSE)
[![Status: release candidate](https://img.shields.io/badge/status-1.0.0--rc.1-f59e0b)](CHANGELOG.md)
[![Backend: Python 3.12+](https://img.shields.io/badge/backend-Python%203.12%2B-3776ab)](src/backend)
[![Studio: Next.js](https://img.shields.io/badge/studio-Next.js-111827)](src/apps/studio)
[![Self-hosted](https://img.shields.io/badge/deploy-self--hosted-16a34a)](docs/08-implementation/NorthCX_Deployment-Guide.md)

**[Quick start](#-try-it-in-five-minutes)** · **[What you get](#-what-you-get)** · **[How it works](#-how-it-works)** · **[Safety](#-safety-you-can-explain-to-your-risk-team)** · **[Docs](#-documentation)** · **[Status](#-honest-status)**

</div>

---

**NorthCX is an open-source platform for running AI agents that handle real customer conversations and do the work, not just answer questions**: look up the order, issue the refund, update the account, and hand over to a person when they should. It is built on the Claude API and runs on your own infrastructure, so customer data stays where you put it.

Most "AI chat" projects stop at the demo. NorthCX is the other 90%: **every reply and every action is supervised, risky actions wait for a human, every change is tested before customers see it, and every figure can be traced back to the conversations behind it.**

<div align="center">
<img src="docs/assets/studio-console.png" alt="The Studio test console: a customer asks for a 500 refund, the agent calls the refund tool, the platform holds it for approval, and every step shows in the trace" width="92%">
<br><sub><em>A 500 refund is over the agent's limit, so the platform holds it for a person instead of trusting the model. Every step is visible.</em></sub>
</div>

## ✨ What you get

<table>
<tr>
<td width="33%" valign="top">

### 🤖 Agents that act
Define an agent in plain YAML: its instructions, tools, checks, skills and journeys. Typed tools call your systems, with retries, scopes and secrets handling built in. Specialist agents can take over a conversation.

</td>
<td width="33%" valign="top">

### 🛡️ Supervised by design
Replies and tool calls pass through guardrails. Refunds over a limit, account changes and anything else you choose wait for **human approval**. Legal threats, safety issues and complaints always go to a person.

</td>
<td width="33%" valign="top">

### ✅ Proven before release
Scenario simulations (including attack suites), a judge model, immutable versions, a publish checklist and a release gate tied to the exact version. Staged rollouts and one-step rollback.

</td>
</tr>
<tr>
<td valign="top">

### 💬 Every channel
Web chat (drop-in widget and SDK), email, SMS, **WhatsApp**, **Telegram** and phone calls through your telephony bridge. One agent definition, a style per channel, 13 languages detected offline.

</td>
<td valign="top">

### 📚 Knowledge that stays fresh
Import PDF, Word, PowerPoint, Excel, HTML and Markdown, or crawl your help site on a schedule. Answers cite their sources, stale pages are flagged, and hybrid keyword and meaning search is optional.

</td>
<td valign="top">

### 📈 Insight you can trust
Containment, escalation, satisfaction and cost, each shown with its numerator and denominator. Ask questions in plain words; the model picks the figure, the numbers are computed, never generated.

</td>
</tr>
</table>

<details>
<summary><b>The full list</b> (click to expand)</summary>

| Area | Included |
|---|---|
| **Build** | Agents as code, templates for common intents, journeys with enforced step order, skills, per-agent model choice, brand voice and forbidden phrases, **draft an agent from your procedures, transcripts or call recordings**, a form editor with live checks |
| **Supervise** | Input checks (personal-data masking, takeover phrasing, abuse and flood detection), reply guardrails, a supervisor model, per-tool approval rules, tool scopes, one-time-code **identity verification**, token budgets, fail-closed behaviour |
| **People in the loop** | Hand-off queues with business hours, a package with transcript, facts and actions taken, suggested replies for agents, person replies, hand-back to the agent, conversation review with failure tagging, helpdesk integration |
| **Test and release** | Scenarios with assertions, simulated customers with personas, judge scoring, regression scenarios from production traces, environments (dev, staging, production), staged rollout and A/B comparison, rollback |
| **Knowledge and memory** | Sources, freshness, citations, file import, website crawler with schedules, long-term customer memory with recall and erase, history summarisation for long conversations |
| **Observe** | Metrics with denominators, alerts with delivery tracking, always-on monitoring of every turn, conversation search and tags, plain-language analytics with charts, trace export (OpenTelemetry, Langfuse), signed status events |
| **Govern** | Roles and scoped keys, single sign-on (OpenID Connect), hash-chained audit log, privacy export, erasure and retention, data-residency policy checked at start-up, security hardening with standing tests |
| **Run** | Docker Compose stack, Postgres 16 with pgvector, migrations at start, load and cost tools, configuration through environment and files |

</details>

## 🖥️ Studio: the operator console

Everything above is operated from **Studio**, a web console with roles, so reviewers, developers and auditors each see what they need.

<table>
<tr>
<td width="50%"><img src="docs/assets/studio-approvals.png" alt="Approvals queue"><br><sub><b>Approvals.</b> Held actions with the exact input, approve or reject with a note.</sub></td>
<td width="50%"><img src="docs/assets/studio-insights.png" alt="Insights dashboard"><br><sub><b>Insights.</b> Every figure shows what it is a share of; ask questions in plain words.</sub></td>
</tr>
<tr>
<td width="50%"><img src="docs/assets/studio-knowledge.png" alt="Knowledge management"><br><sub><b>Knowledge.</b> Sources, files, crawls and a "try a question" box.</sub></td>
<td width="50%"><img src="docs/assets/studio-versions.png" alt="Versions and releases"><br><sub><b>Versions and releases.</b> Immutable versions, checklist, gate, staged rollout, rollback.</sub></td>
</tr>
</table>

## 🧭 How it works

```mermaid
flowchart LR
    C["Customer<br/>web · email · SMS<br/>WhatsApp · Telegram · voice"] --> IN["Input checks<br/>PII masking · injection<br/>abuse · hand-off topics"]
    IN --> R["Agent runtime<br/>Claude + typed tools"]
    R --> T["Your systems<br/>orders · billing · CRM"]
    R --> G["Reply guardrails<br/>+ supervisor"]
    R -. "risky action" .-> A["Human approval"]
    R -. "needs a person" .-> H["Hand-off queue<br/>+ helpdesk"]
    G --> C
    A --> R
    R --> TR[("Traces · audit log<br/>metrics · events")]
    S["Studio<br/>build · test · release · review"] --> R
    TR --> S
```

1. **A customer writes** on any channel. The message is screened before the model sees it: personal data is masked, takeover attempts and abuse are caught, and topics you listed (legal, safety, complaints) go straight to a person.
2. **The agent works**: it reads your knowledge, calls your systems through typed tools, and remembers what it should. Every step is traced.
3. **Risky things wait.** A tool call that needs approval is held with its exact input until a person decides; the conversation resumes either way.
4. **Replies are checked** by your rules and, if you choose, a supervisor model, before the customer sees them. If anything fails, the platform fails closed and hands over.
5. **You learn from it**: review conversations, tag failures, turn them into regression scenarios, and release the fix through the same gates as any change.

## 🛡️ Safety you can explain to your risk team

| Question | Answer |
|---|---|
| *What stops the agent doing something expensive?* | Per-tool, per-input approval rules; tool scopes (identified customers only, specific channels, verified identity); idempotency keys so approved actions run once |
| *What if someone tries to hijack it?* | Input and tool-output screening, attack scenario suites that run in CI, tool results treated as untrusted data, and the controls that matter (approvals, scopes, supervisors) do not depend on the model behaving |
| *What if the model is down or unsure?* | Retries, optional fallback model, then a graceful hand-off to a person; supervisor errors fail closed |
| *Where does customer data go?* | Only where you configure. A residency policy file lists allowed regions and is checked at start-up; Studio shows every destination and what it receives |
| *Can we prove what happened?* | Per-run traces, a tamper-evident audit log, release records tied to the exact version, and status events for your own systems |
| *Can customers be erased?* | Export, erase and retention rules per customer and per conversation, covering every store |

Read the [threat model](docs/06-security/NorthCX_Threat-Model.md) and [security review](docs/06-security/NorthCX_Security-Review.md) for the detail, including what is **not** covered.

## 🚀 Try it in five minutes

No API key needed: an offline demo model lets you click through the whole console.

```bash
git clone https://github.com/VenkataAnilKumar/NorthCX.git && cd NorthCX
cp .env.example .env
# edit .env: set NORTHCX_DB_PASSWORD (letters and digits), NORTHCX_API_KEY (a long random value), and NORTHCX_DEMO=1
docker compose up -d --build --wait
# Studio: http://localhost:3001  (Settings → paste the API key)      API: http://localhost:3000
```

The demo model is a handful of keyword rules, not an AI. Try *"where is order 1042?"*, *"refund 500 for order 1042"* (over the limit, so it waits for approval) and *"I want a person"*, then look at **Approvals**, **Handoffs** and **Insights**.

For real conversations, set `ANTHROPIC_API_KEY` instead of `NORTHCX_DEMO=1` and write your own agent, starting from a template or from your own procedures.

<details>
<summary><b>An agent is just a file</b> (the shipped example)</summary>

```yaml
id: support
instructions: |
  You are a customer support agent for an online store.
  Be concise and friendly. Use tools to check facts before answering; never guess order details.
  Refunds above 100 require human approval, which the system handles.
  Never reveal payment card numbers. If you cannot help, hand off to a human.
tools: [lookup_order, issue_refund]
guardrails: [no_card_numbers]
forced_handoff:
  - name: legal
    patterns: ['\b(lawyer|attorney|lawsuit|sue|suing|legal action)\b']
    reply: I'm passing this to a person on our team who can discuss it with you directly.
input_guardrails:
  - { name: pii_detection, config: { mask_pii: true } }
  - prompt_injection
output_guardrails: [tool_output_injection]
```

Versions are immutable, tested by scenarios, and released through a gate. See [`src/backend/examples/`](src/backend/examples) for the agent, its tools and its scenarios.

</details>

<details>
<summary><b>Run from source</b></summary>

```bash
# backend
cd src/backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python -m pytest        # Postgres-backed tests are skipped without a database (NORTHCX_REQUIRE_DB=1 makes them fail instead)
NORTHCX_DEMO=1 NORTHCX_API_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(32))") python -m northcx     # http://localhost:3000
# Postgres storage: add NORTHCX_DATABASE_URL=postgresql://northcx:northcx@localhost:5432/northcx (migrations run at start;
# meaning-based search additionally needs the pgvector extension)

# Studio
cd src && npm ci && npm test && NORTHCX_API_URL=http://localhost:3000 npm run dev      # http://localhost:3001 (npm workspaces: apps/studio and the shared packages)

# browser SDK and widget
cd src/sdk && npm ci && npm test && npm run build
```

</details>

## 📦 Put it on your website

The browser SDK and a drop-in `<northcx-chat>` widget have no runtime dependencies and stream replies, retry, renew tokens, accept uploads and show teammate replies. Your server mints a short-lived chat token for the signed-in customer, so the agent knows who it is talking to. See the [client SDK guide](docs/05-technical/NorthCX_Client-SDK.md).

## 📊 Honest status

**NorthCX is a release candidate (1.0.0-rc.1).** The feature set is complete and covered by more than 1,300 backend tests plus Studio and SDK tests, browser smoke tests and a clean-checkout verification. Before you rely on it:

| | |
|---|---|
| ✅ **Ready** | Everything in the feature list above, built, tested and documented |
| ⚠️ **Not yet done** | An independent penetration test; a pass with a live model (everything so far ran against scripted and offline models); judge calibration with a real model |
| 🧱 **By design (for now)** | One company and one region per deployment (multi-tenancy, metering and billing are on the roadmap, not built) |

Read the [security review](docs/06-security/NorthCX_Security-Review.md) and the [release checklist](docs/08-implementation/NorthCX_Release-Checklist.md) before exposing it to the public internet.

## 📚 Documentation

| You want to | Read |
|---|---|
| Deploy it | [Deployment guide](docs/08-implementation/NorthCX_Deployment-Guide.md) (every setting), [Performance](docs/08-implementation/NorthCX_Performance.md) |
| Write and test agents | [Agent runtime](docs/04-ai-architecture/NorthCX_Agent-Runtime.md), [Guardrails](docs/04-ai-architecture/NorthCX_Guardrails-and-Supervisors.md), [Simulation and evals](docs/04-ai-architecture/NorthCX_Simulation-and-Evals.md), [Studio](docs/07-design/NorthCX_Studio.md) |
| Connect channels | [Channels and voice](docs/05-technical/NorthCX_Channels-and-Voice.md), [Voice](docs/05-technical/NorthCX_Voice.md), [Client SDK](docs/05-technical/NorthCX_Client-SDK.md) |
| Connect your systems | [Integrations](docs/05-technical/NorthCX_Integrations.md), [API design](docs/05-technical/NorthCX_API-Design.md) |
| Manage knowledge | [Knowledge design](docs/05-technical/NorthCX_Knowledge-Design.md) |
| Measure and monitor | [Observability](docs/05-technical/NorthCX_Observability.md) |
| Judge the security | [Threat model](docs/06-security/NorthCX_Threat-Model.md), [Security review](docs/06-security/NorthCX_Security-Review.md), [`SECURITY.md`](SECURITY.md) |
| See what is built | [Feature catalog](docs/03-specs/NorthCX_Feature-Catalog.md), [Decision log](docs/09-project/NorthCX_Decision-Log.md), [`CHANGELOG.md`](CHANGELOG.md) |
| Contribute | [`CONTRIBUTING.md`](CONTRIBUTING.md), [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) |

Start at [`docs/README.md`](docs/README.md) for the full map.

## 🗂️ Repository layout

| Path | Contents |
|---|---|
| `src/backend/` | Python backend (FastAPI): runtime, guardrails, stores, server, channels, tools (`loadtest`, `cost`, `simulation`, `voice_sim`), example agent, tests |
| `src/apps/studio/` | Studio, the operator console (Next.js); more apps (staff workspace, admin, ops) are planned as separate apps |
| `src/packages/` | Code shared by the web apps: `ui` (components) and `api-client` (typed API client and session helpers) |
| `src/sdk/` | Browser SDK and `<northcx-chat>` widget (TypeScript, no runtime dependencies) |
| `src/prototype/` | TypeScript reference implementation of the runtime semantics |
| `docs/` | Documentation, including the screenshots in `docs/assets/` |

## 🤝 Contributing

Issues, ideas and pull requests are welcome. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md); security reports go through [`SECURITY.md`](SECURITY.md), not public issues.

## 📄 Licence

Apache-2.0. See [`LICENSE`](LICENSE); copied code keeps its own notices ([`NOTICE`](NOTICE), [`THIRD_PARTY.md`](THIRD_PARTY.md)).

<div align="center"><sub>Built on the Claude API · self-hosted · your data stays yours</sub></div>
