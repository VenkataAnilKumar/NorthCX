# NorthCX Agent Platform Research

Status: **Reference**. Updated: 2026-11-18. Master for: the named research behind the Agent Platform design (protocols, open-source reference projects and commercial products studied, the lessons taken and the gaps found). It lives in `00-reference/` because it names other companies' products; the design itself, `../00-platform/NorthCX_Agent-Platform-Design.md`, keeps only the conclusions (its sections 2, 2a and 2b). The list of sources with links is `NorthCX_Reference-Sources.md`.

These sections were moved here unchanged from the design on 2026-11-18. Facts about other products come from search summaries, project pages and vendor material and are directional.

## 2. What the research found

Verification: **repo** means read in this repository; **vendor/search** means a vendor page or a search summary (directional only); **not verified** means background knowledge.

| Topic | Finding | Source quality |
|---|---|---|
| MCP | Spec revision 2026-07-28 is final. It is stateless (no initialize handshake or session header, so any server instance can serve a request), hardens authorization (issuer validation), and formalises extensions (Tasks, MCP Apps). Tool annotations and elicitation were not confirmed. | search of MCP blog and spec pages |
| AG-UI | Typed event stream. Human approval is an **interrupt**: the run ends with `RUN_FINISHED` carrying an `interrupt` outcome (id, reason, message; reason `tool_call` references a prior tool call), and the client starts a new run with a `resume` array answering every open interrupt. | search of AG-UI docs |
| assistant-ui | MIT React chat library with tool UI and inline approvals; works with AG-UI and custom data-stream backends. Its own AG-UI runtime docs could not be reached. | GitHub page |
| Activepieces | Integrations ("pieces") are TypeScript packages with one auth definition, actions and triggers; action and trigger names are permanent because flows store them. Embedding and multi-tenant details were not confirmed. | docs via search |
| Durable approvals | Temporal models a wait for approval as a signal with a timeout, with no compute used while waiting. Limits: deterministic workflow code, and a history cap of 51,200 events or 50 MB. | Temporal docs via search |
| Competitors | Sierra Journeys and Decagon AOPs are natural-language procedures compiled to structured logic, with generation from existing procedures or transcripts; Intercom replaced Tasks with Procedures (March 2026), keeps Workflows for linear canvas flows, and simulates procedures on past conversations. | vendor pages, unverified |

## 2a. Lessons taken from the reference projects

The projects below were read through GitHub pages and search summaries; no code was read or copied when these lessons were taken. Each lesson names the design decision it changed. "Inferred" means the lesson is my reading of a feature list, not something confirmed in code.

| Reference | Lesson | Decision it changes |
|---|---|---|
| **Sim** (workflow builder; Next.js, Zustand, TanStack Query, React Flow; 280+ integrations with triggers and actions) | An integration is a bundle of **actions and triggers**, browsed in one catalogue next to the canvas | The connection catalogue (section 5) lists triggers as well as tools; Automations and Studio both read it |
| **Hermes Agent** (one gateway process for many messaging platforms; session search with FTS5 plus summaries; cron with delivery to chat; skills improved from use) | Channels, scheduled jobs and memory share one gateway and one session model | Chat sessions stay channel-neutral (section 6); scheduled results are delivered only to staff destinations the administrator set up, never to customers (NorthCX's existing `notify` rule); skills-from-use is a Studio suggestion that goes through the normal draft, test and release path, never self-applied |
| **LobeHub** (agent config bundles role, model, skills, connectors, memory; team modes sequential, parallel, debate; reviewable editable memory; resource library) | Agent setup is one screen; memory should be visible and editable by a person | Studio's agent inspector shows model, tools from the catalogue, knowledge and memory settings together; memory view with delete stays a requirement. Team modes are **not** adopted (specialist routing already exists and supervision is simpler) |
| **LibreChat** (branching, edit and resubmit, file chat, artifacts, MCP) | Staff need to re-run a conversation from an earlier turn with a changed message | Studio test console and Pilot get edit-and-rerun from a turn (staff surfaces only; customer conversations are never edited) |
| **Agno AgentOS** (runtime exposed as an API with 50+ endpoints, SSE and websockets, JWT RBAC, OpenTelemetry) | Treat the runtime as a documented API product, not an internal detail | Agent API section 4: publish the contract (OpenAPI is already generated) and version it; every UI uses only it |
| **OpenGeni** (durable, replayable sessions; approvals; Postgres event history and audit; managed sandboxes) | Sessions should be observable, interruptible and replayable from stored events | Add **session replay** from stored trace events to Studio (also useful for simulation regression); confirms the approval and audit model |
| **Onyx** (40 to 50+ connectors; permission-aware search is paid) | Connector breadth is a buying criterion, and per-user permissions are the hard part | Integrations roadmap ranks connectors by the first customers' systems; the gateway carries the **acting identity** so a staff tool call runs with that person's rights (the `Tool.audience` and `permission` fields already model this) |
| **Cognee** (graph plus vector memory; REST, MCP, SDK) | Memory can improve by relationships, not only recall | Memory backend stays behind `MemoryStore`; trial Cognee as one implementation, not a dependency of the four modules |
| **Agenta** (prompt versions, side-by-side comparison, LLM-as-judge, OTel traces) | Compare two versions on the same cases before release | Studio release view adds a side-by-side of the live and candidate versions on the same scenarios (the improvement loop already runs both; surface it) |
| **Jan** (OpenAI-compatible local server on localhost; extensions) | A local model is just another OpenAI-compatible endpoint | No new work: the existing OpenAI-compatible provider is the path; document how to point it at a local server |
| **Intercom Fin, Sierra, Decagon** (procedures compiled to structured logic; simulate on past conversations) | Authors write plain-language procedures; the platform enforces them | Studio procedure-first authoring and simulation from past conversations (section 7) |
| **Macro, Busabase, Rerun, Eigent, Orkas, holaOS, Kuse** (inferred: shared workspaces for people and agents, desktop agent teams) | Mostly employee-side or developer-side products | Informs the later Workspace, not these four modules |

What was **not** adopted, and why: autonomous general-purpose agent behaviour (Hermes, Suna, Eigent) conflicts with the supervised, permission-bound model; team and debate modes add behaviour that is hard to test and approve; copying any project's code (the project policy records that nothing is copied).

## 2b. Product reference model: Fin, Sierra and Decagon

NorthCX is positioned as the self-hosted, inspectable counterpart of Intercom Fin, Sierra and Decagon. All three run the same loop: **teach** (plain-language procedures), **test** (simulations before launch), **deploy** (every channel), **monitor and improve** (insights, always-on quality checks, suggestions). Facts come from vendor pages and third-party reviews and are directional.

Gaps found against NorthCX (the repo column was checked in this repository):

| Gap | Reference behaviour | NorthCX today (repo) | Where it is designed |
|---|---|---|---|
| Native connectors to systems of record | All three integrate natively with helpdesks and CRMs | YAML connectors, a Chatwoot adapter, no MCP yet | Section 5 |
| Guided authoring for non-engineers | Procedures and Journeys written in plain language, generated from existing material | Drafts from procedures and recordings exist; no guided path | Section 7 |
| Plain-language quality criteria | Decagon Watchtower checks live conversations against criteria written in plain language | Quality rubric is a list of deterministic checks (`qa.py`); a model verdict is on request only | Section 7 (author-written criteria that run as model-judged checks, with the deterministic rubric kept as the baseline) |
| Segment-aware guidance | Fin Guidance sets tone and rules by segment or product line | Brand voice, forbidden phrases and per-channel styles | Section 7 (guidance sets attached to segments) |
| Scheduled and CI simulations with alerts | Decagon runs simulations on a schedule or in CI and alerts | Scenarios run in CI as a build gate (`ci.yml`); no scheduled production runs found in the simulation, regression or monitor code | Section 8: a scheduled routine that runs the live agent's scenarios and notifies a destination |
| Proactive suggestions | Fin Suggestions, Sierra monitors | "Improve this agent" on request | Section 7 (surface findings as a feed; changes still go through draft, test, release) |
| Voice | Native voice in all three | Conversation side built; speech and telephony are an operator bridge | Out of scope for the four modules; decide separately |
| Outcome pricing | Per outcome or resolution | Not built | Blocked on D1 |

Where NorthCX should not copy them: managed per-outcome SaaS (self-hosted first), closed workflows (inspectability is the edge), and opaque decisions (reviewers of those products report difficulty understanding individual decisions in real time, which NorthCX's traces and audit log are meant to answer).
