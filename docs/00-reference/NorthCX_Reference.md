# NorthCX Reference: Sierra AI Analysis and Open-Source Building Blocks

> **Status and confidence.** sierra.ai, docs.sierra.ai, onyx.app, sim.ai, kortix.com and agno.com were not reachable from the research environment (network policy). Everything below comes from third-party reviews, search summaries, GitHub mirrors and background knowledge. **Verify licenses, versions and feature claims against each official repo/doc before committing to a dependency.** Re-run this research once the domains are allowed.

Date: 2026-11-02

---

## 1. Sierra AI: what we are replicating

Sierra (founded 2023 by Bret Taylor and Clay Bavor) sells enterprise customer-experience agents that resolve issues autonomously and are priced by outcome.

### 1.1 Product features
| Area | Features |
|---|---|
| Agent behavior | Autonomous resolution with actions (refunds, returns, plan changes); goals and guardrails in natural language instead of flowcharts; multi-step tool use; human handoff with context |
| Channels | Web chat, mobile chat, voice, email, SMS, WhatsApp, ChatGPT; one agent definition across channels |
| Build surfaces | **Agent SDK** (code-first, declarative, composable skills, multi-agent, CI/CD); **Agent Studio** (low-code, Journeys, knowledge management, Agent Traces); **Ghostwriter** (agent that builds agents) |
| Trust and quality | Supervisor models checking reasoning/outputs; simulation testing before release; SOC 2, ISO 27001, HIPAA, GDPR; multi-vendor model failover |
| Data and ops | Agent Data Platform (cross-session memory); Insights (analytics/QA); Live Assist (human-agent copilot); outcome-based pricing |

### 1.2 Architecture (as reported)
- **Constellation of models:** routing across many LLMs (reviews cite 15+; single-source claim) with failover.
- **Supervisor models** review the main agent's output against policy.
- **Goals and guardrails**, not scripted decision trees.
- **Tool/action layer** into CRM, order, billing systems.
- **Simulation-driven testing** (related: Sierra's τ-bench).
- **Tech stack:** not publicly documented beyond the above. Do not assume more.
- **Access:** SDK and docs may be gated to contracted customers.

---

## 2. Candidate open-source building blocks

### 2.1 Platform candidates you named
| Project | What it is | License | Sierra counterpart | Fit |
|---|---|---|---|---|
| **Agno** | Python agent framework + AgentOS runtime: teams, memory, guardrails, HITL, tracing, evals, JWT RBAC, MCP, scheduling, control-plane UI; runs in your VPC | Apache-2.0 | Agent SDK / Agent OS | Best runtime match |
| **Sim** (simstudioai/sim) | Visual agent workflow builder: Next.js, Postgres + Drizzle, ReactFlow; branching/loops; deploy as API/webhook/schedule; tracing | Apache-2.0 | Agent Studio / Journeys | Good (Studio) |
| **Onyx** | Self-hosted chat + RAG: 40+ connectors, agents, MCP, deep research; Next.js frontend, API backend, model server, workers | MIT outside `ee/` | Knowledge management | Partial (retrieval layer) |
| **Kortix / Suna** | General autonomous agent: FastAPI, Next.js, Supabase, LiteLLM, Docker sandboxes (Daytona), browser automation | Apache-2.0 | Little | Weak (open-ended tasks, not scoped CX) |

### 2.2 Components for the remaining features
| Feature | Option | License | Notes |
|---|---|---|---|
| Voice | **Pipecat** | BSD-2 | Python real-time voice/multimodal framework; cleanest license |
| Voice | **LiveKit Agents** | Apache-2.0 + caveats | WebRTC SFU based; turn-detection models under separate license tied to LiveKit Agents; read LICENSE |
| Omnichannel inbox + human handoff | **Chatwoot** | MIT core | Web chat, email, WhatsApp, SMS, Telegram, Instagram; agent inbox; not every feature is MIT |
| Observability / evals | **Langfuse** | MIT core, commercial `ee/` | Tracing, datasets, LLM-as-judge, OTel ingest; needs Postgres, ClickHouse, Redis, object storage |
| Observability / evals | Arize Phoenix | Elastic License 2.0 | Source-available; bars offering as hosted service |
| Guardrails | **NeMo Guardrails** | Apache-2.0 | Input/dialog/retrieval/execution/output rails in Colang; built-in rails are a starting point |
| Memory | **Mem0** | Apache-2.0 | Drop-in memory layer, bring-your-own vector store |
| Memory | Letta | Apache-2.0 | Self-managing agent memory |
| Memory | Graphiti (Zep OSS) | Apache-2.0 | Temporal knowledge graph; needs a graph DB |

### 2.3 Known gaps (not found or not searched)
- **Conversation simulation testing:** no suitable OSS found (Garak and PyRIT are red-teaming tools). Build in-house.
- **Durable workflows** (Temporal, Inngest): not researched.
- **Guardrails AI** license: unconfirmed.
- **CX connectors** (Zendesk, Shopify, Salesforce, etc.): not researched.
- **Outcome-based billing:** nothing found; build in-house.

---

## 3. Feature-to-component map

| Sierra capability | Chosen / proposed component | Status |
|---|---|---|
| Agent runtime, tools, goals + guardrails | `src/core` (TypeScript) or Agno (Python) | `src/core` scaffolded |
| Supervisor models | `src/core/guardrails.ts` (+ optional NeMo Guardrails) | Scaffolded |
| Human approval / handoff | `src/core/runtime.ts` + Chatwoot inbox | Runtime done; Chatwoot not wired |
| Traces | `src/core/trace.ts` exported to Langfuse (OTel) | In-memory/JSONL only |
| Memory | `MemoryStore` interface; Mem0 behind it | Interface + in-memory only |
| Knowledge / RAG | Onyx behind a tool | Not started |
| Studio (low-code) | Sim, or custom UI | Not started |
| Voice | Pipecat + Claude + telephony provider | Not started |
| Web chat / email / SMS / WhatsApp | HTTP API + Chatwoot channel adapters | Not started |
| Simulation testing | In-house (`src/sim`) | Not started |
| Insights / analytics | Langfuse + custom dashboards | Not started |
| Ghostwriter | Claude-driven agent that emits `defineAgent` configs | Not started |
| Outcome-based billing | In-house | Not started |

## 4. Decisions still open
1. **Runtime language:** Agno (Python) vs. current TypeScript core. Sim and the scaffold are TypeScript; Agno, Pipecat, NeMo and Mem0 are Python.
2. **Studio:** adopt Sim vs. build a thin UI.
3. **Re-verification:** allow the blocked domains in the environment's network settings, then check official docs and LICENSE files.

## 5. Suggested build order
1. Server API + web chat channel on `src/core`.
2. Simulation testing (`src/sim`) and an example support agent.
3. Langfuse tracing export and Mem0 memory adapter.
4. Chatwoot channel and handoff integration.
5. Studio (Sim or custom), Onyx retrieval tool.
6. Voice via Pipecat.

## 6. Sources
- Sierra: [api-evangelist/sierra-ai](https://github.com/api-evangelist/sierra-ai), [eesel.ai](https://www.eesel.ai/blog/sierra-ai), [Contrary Research](https://research.contrary.com/company/sierra), [Cheeky Pint interview](https://cheekypint.substack.com/p/bret-taylor-of-sierra-on-ai-agents), [Macha](https://www.getmacha.com/blog/sierra-ai-complete-guide), [myaskai](https://myaskai.com/blog/sierra-ai-complete-guide-2026), [TAAFT](https://theresanaiforthat.com/ai/sierra-agent-os/)
- Onyx: [openapps.pro](https://openapps.pro/apps/onyx)
- Sim: [jimmysong.io](https://jimmysong.io/ai/sim-studio), [landscape](https://landscape.jimmysong.io/projects/sim-studio/)
- Kortix/Suna: [jimmysong.io](https://jimmysong.io/ai/suna), [sourcepulse](https://www.sourcepulse.org/projects/2356668)
- Agno: [PyPI](https://www.pypi.org/project/agno), [rywalker.com](https://rywalker.com/research/agno), [developersdigest](https://www.developersdigest.tech/agent-frameworks/agno)
- Voice: [Cekura](https://www.cekura.ai/blogs/pipecat-vs-livekit-the-real-difference), [Forasoft](https://www.forasoft.com/blog/article/pipecat-vs-livekit-agents)
- Chatwoot: [Macha](https://www.getmacha.com/blog/what-is-chatwoot)
- Observability: [Phoenix vs Langfuse](https://futureagi.com/blog/arize-phoenix-vs-langfuse-2026/), [Prem AI](https://blog.premai.io/llm-observability-setting-up-langfuse-langsmith-helicone-phoenix)
- Guardrails: [NeMo Guardrails (PyPI)](https://pypi.org/project/nemoguardrails/), [NVIDIA](https://developer.nvidia.com/neMo-guardrails)
- Memory: [Mem0 vs Zep vs Letta](https://toolfreebie.com/?p=327), [Mem0 vs Letta](https://vectorize.io/articles/mem0-vs-letta)

---

## 7. Competitive comparison (moved from the market doc)

Details are third-party summaries and **unverified**.

| Dimension | Sierra (reported) | Agno | Sim | Onyx | NorthCX (target) |
|---|---|---|---|---|---|
| Open source | No | Yes (Apache-2.0) | Yes (Apache-2.0) | Yes (MIT, `ee/` excluded) | Yes |
| CX-specific out of the box | Yes | No | No | No | Yes |
| Omnichannel incl. voice | Yes | Build it | Build it | Limited | Phased (chat first) |
| Supervisor / guardrails | Yes | Guardrails | Limited | Limited | Yes |
| Simulation testing | Yes | Evals | No | No | Yes (planned) |
| Low-code builder | Yes | Control plane UI | Yes | Agent builder | Phase 4 |
| Self-host | Unclear | Yes | Yes | Yes | Yes |

Segments: enterprise CX agent platforms (Sierra, direct benchmark); incumbent helpdesk AI; open-source frameworks (Agno), workflow builders (Sim), knowledge/chat (Onyx); general agent platforms (Kortix/Suna, different use case). Sierra's reported outcome-based pricing informs the pricing options in `01-product`.

## 8. Proposed component selections (moved from the technical docs)

| # | Capability | Candidate selected | Alternatives | Rationale / notes |
|---|---|---|---|---|
| D1 | Runtime language | TypeScript (own runtime) | Python with Agno | Scaffold exists; shares language with a web Studio and Sim |
| D7 | Observability | Langfuse via OpenTelemetry | Phoenix (source-available) | Permissive core licence |
| D8 | Memory | Mem0 behind `MemoryStore` | Letta, Graphiti | Apache-2.0; pluggable |
| D9 | Knowledge / RAG | Onyx as a retrieval service | Own pgvector | Reuse connectors; verify `ee/` split |
| D10 | Channels / human inbox | Chatwoot | Build own inbox | Email, SMS, WhatsApp, live chat |
| D11 | Voice | Pipecat | LiveKit Agents | BSD-2; avoids LiveKit model-licence caveat |
| D12 | Studio | Sim, or custom | Build | Decide at Phase 4 |
| D13 | Supervisor | Own LLM supervisor; NeMo Guardrails optional | NeMo only | Simple first |

Python components (Pipecat, NeMo Guardrails, Mem0, Agno) would run as separate services behind HTTP.

Build vs adopt: **build** the runtime, supervisor, simulation testing, outcome billing (later). **Adopt** memory (Mem0), knowledge (Onyx), observability (Langfuse), inbox (Chatwoot), voice (Pipecat). **Decide later** Studio (Sim or custom). **Evaluate** Agno only if switching to Python. **Skip** Kortix/Suna. **Research** durable workflows (Temporal, Inngest) and CX connectors.

Licence cautions to review before use: Onyx `ee/`, Langfuse `ee/`, Chatwoot enterprise features, LiveKit model licence, Phoenix ELv2.

---

## 9. Additional feature research (web search, 2026-11-02)

Search snippets and vendor marketing pages; **unverified**. Used as input to `03-specs/NorthCX_Feature-Catalog.md`.

### Sierra components reported
| Component | Reported detail |
|---|---|
| Ghostwriter | Agent-building agent (launched March 2026): turns procedures and recordings into production agents for voice, chat and email, 30+ languages; reduces manual journey editing, integrations, simulations and issue triage |
| Voice | Phone support replacing rigid IVR menus; 55+ languages with mid-call language switching (third-party claim) |
| Live Assist | Real-time guidance for human agents: next-step suggestions, drafted replies and call scripts |
| Insights | Analytics, experimentation and observability; Explorer answers analytics questions in plain language |
| Agent Data Platform | Persistent memory layer (customer history, CRM records); reportedly fronted by a product called Context Engine |
| Journeys | Composable building blocks with goals and guardrails; Agent Studio 2.0 lets users describe journeys in natural language |
| Agent SDK | Goals and reusable skills (for example triage, respond, confirm) composed into workflows; adjustable workflow flexibility; secure connection to internal and external systems; simulations to catch regressions; journeys as code with change tracking; one build deployed to chat, phone, email, SMS and messaging; debugging via API-call and logic traces |
| Release management | No versioning, environments, promotion or rollback details found |
| Lineup caveat | Sources disagree on whether Agent OS and Agent SDK are product names or developer terms |

### Market checklist themes (vendor guides)
- Handoff continues the conversation with history and customer profile; the customer never repeats themselves.
- Monitoring covers every AI interaction, not a sample.
- A defined list of topics the AI must never handle alone (for example complaints, legal matters).
- Analytics: containment rate, CSAT, intent gaps, workflow failure points.
- A/B tests or staged rollouts before changes go live.
- Simulation runs after knowledge changes; tests use real, messy conversations.

### Sources
- [Sierra: Agent SDK](https://sierra.ai/product/agent-sdk), [Sierra: Build your AI agent](https://sierra.ai/product/build-your-ai-agent), [Sierra blog: Agents as a service](https://sierra.ai/blog/agents-as-a-service)
- [sitegpt.ai review](https://sitegpt.ai/resources/sierra-review), [Atlan: Sierra platform](https://atlan.com/know/ai-agent/ai-agent-applications/what-is-sierra-ai/), [agentsindex.ai](https://agentsindex.ai/sierra), [apis.io](https://apis.io/providers/sierra/)
- Checklists: [Qiscus](https://www.qiscus.com/en/blog/ai-customer-service-platform-evaluation-checklist/), [No Jitter](https://www.nojitter.com/ai-automation/ai-agents-require-guardrails-testing-and-visibility), [QuickBlox](https://quickblox.com/answers/ai-agent-platform-checklist/), [Infobip](https://www.infobip.com/blog/how-to-choose-chatbot-platform), [Cresta](https://cresta.com/guides/ai-voice-agents-customer-support)
