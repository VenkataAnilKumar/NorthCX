# NorthCX Tool Gateway (Phase 1)

Status: **Built** for WP 1.1, 1.2, 1.4 and 1.6a; WP 1.6b not started. Updated: 2026-11-19. Master for: how tools from any source reach agents, what the runtime already guarantees for every tool, and the work packages of Phase 1 of `../12-project/NorthCX_Agent-Platform-Plan.md`. Part of `../00-platform/NorthCX_Agent-Platform-Design.md` section 5.

Phase 1 changes no behaviour a user can see. The existing test suite is its safety net.

## 1. Research: what the code does today
Read in this repository on 2026-11-19.

- **Tools reach agents through one map.** `Registry` (`northcx/spec.py`) maps a tool name to a `Tool` (`northcx/agent.py`). Agents and skills refer to tools by name; `Registry.validate` rejects unknown names and keeps staff tools away from customer agents.
- **Tools come from six places today,** each added by hand: the deployment's own registry function (`NORTHCX_REGISTRY`), YAML connectors (`NORTHCX_CONNECTORS_DIR`), identity verification, knowledge search and customer memory (all in `bootstrap/agents.py`), and the staff tools, Pilot proposals included (`register_staff_tools` in `workspace.py`, which also renames the staff knowledge search). Duplicate names are handled two ways: connectors refuse a name that exists, the others skip it silently. Skills are not tools; they only refer to tools by name.
- **Every tool, whatever its source, gets the same treatment from the runtime** (`Runtime._run` in `runtime.py`): input validated against the tool's model; the agent's guardrails run, including tool scopes (channel, verified identity); an approval is requested if `requires_approval` returns a reason; in a simulation a write tool is replaced by its dry-run result; a repeated write in one turn is answered from the first result; a stable idempotency key is passed; secrets are redacted from results, traces and stored messages; the agent's output guardrails screen the result before the model reads it. After a person approves, `ApprovalFlow._execute` re-checks and runs the same `Tool` with the context of the turn that asked (fixed on 2026-11-18, pull request #7).
- **Source-specific safety lives in the source.** The YAML connector enforces the operator's host allowlist, https, no redirects, timeouts, response size caps and OAuth token handling (`northcx/connectors.py`).
- **What a tool does not know today:** where it came from. `Registry.describe()` and the trace's `tool_call` event carry no source, the set of tools is fixed at start-up, and nothing detects a tool whose definition changed. A tool server that can change its tools after approval (MCP, Phase 2) needs all three.
- **The HTTP API** has 273 operations in `docs/api/openapi.json`, generated from the code and checked by `tests/test_docs_in_sync.py`. The agent-facing groups are `agents` (26), `sessions` (10), `simulations` (10), `handoffs` (6), `approvals` (3), `traces` (3) and `events` (3). Nothing states which routes other software may rely on, or what may change within `/v1`.

## 2. What this changes in the plan
- **WP 1.3 is already true.** The runtime applies approvals, scopes, dry-run, secrets and output screening to every `Tool`. A second "gateway" layer in front of it would repeat those checks and could drift from them; it would be dead code. WP 1.3 is folded into WP 1.4, which proves the guarantees for every source.
- **WP 1.5 (acting identity) is deferred.** `ToolContext.actor` exists and staff tools use it. Approvals do not store the actor, so a staff tool that needed approval would fail at execution, but no staff tool needs approval (the Pilot's Do style uses its own confirmation). It returns with the first work package that needs it (Phase 5, the `tool` step).
- **The `ToolSource` interface waits for MCP.** One implementation of an interface is not an abstraction yet. Phase 1 adds what every source needs now (a source label on each tool, one registration function, a fingerprint). The interface, with discovery and refresh, is designed with the MCP client in WP 2.1, when its second real use exists.

## 3. Requirements
| ID | For whom | What | Acceptance check |
|---|---|---|---|
| G1 | Anyone adding tools | Each tool records its source; every source is registered through one function that refuses a duplicate name the same way and names both sources | A test registers two sources with the same tool name and gets one error naming both |
| G2 | A reviewer reading a trace; an author choosing tools | The source is shown on each tool in `Registry.describe()` and on each `tool_call` trace event | Tests read it from both; existing consumers of both still pass unchanged (the field is additive) |
| G3 | A security reviewer | A tool has a fingerprint that changes when its name, description, input schema, effect, audience, permission or whether it needs approval changes | Tests change each in turn and see a different fingerprint; the same definition gives the same fingerprint across processes |
| G4 | Everyone | No visible behaviour change | The whole existing backend suite passes with no edits to existing tests |
| G5 | The MCP work (WP 2.1) | A conformance suite proves the runtime's guarantees for the tools of any source: input validated, scope blocks, approval held, dry-run in simulation, a duplicate write runs once, secrets redacted, output screened, the idempotency key unchanged from the request to the approved execution | It runs against the YAML connector source and against a second source defined in the test. Safety that belongs to one source (the connector's host allowlist and redirect refusal) stays in that source's own tests; the MCP source (WP 2.1) needs its own |
| G6 | Developers building on the API | The Agent API is a stated set of routes with a stability rule: within `/v1` fields may be added, never removed or retyped | A test compares those routes' parameters and request bodies with a checked-in snapshot; the comparison reports a removal, a type change or a newly required field and not an addition (responses only where typed, WP 1.6a and 1.6b) |

## 4. Design
- **Operators:** no new setting and no new screen. A duplicate tool name stops start-up as it does today, now saying which two sources clash (for example "Tool 'lookup_order' from connectors:/etc/northcx/connectors is already registered by the registry function").
- **Catalogue and traces (G2):** one more field, `source`, one of `registry`, `connectors`, `verification`, `knowledge`, `memory` or `staff`. It never contains a secret, a URL or a path that includes a secret.
- **Fingerprint (G3):** a short hash shown only in the catalogue; later used to pin MCP tool lists. It covers a tool's definition, not its credentials or its server address (those belong to the connection, WP 2.3).
- **Agent API (G6):** the contract covers chat and streaming chat, sessions, approvals, hand-offs, versions, releases, simulation runs, traces and events. The snapshot is `docs/api/agent-api-v1.json`; the rule is written in the API Design document.

## 5. Architecture
- `Tool` gets `source: str` (default `"registry"`). `Registry.add_tools(source, tools)` sets it, refuses duplicates, and is used by every place that registers tools today; `bootstrap/agents.py` no longer registers tools one by one. Connectors refuse a name that is taken; the built-in sources (verification, knowledge, memory, staff) still yield to a deployment's own tool of the same name, as before, and say so in the code.
- `tool_fingerprint(tool)` is a function in `northcx/agent.py`: SHA-256 of a canonical JSON form of the fields in G3.
- The runtime adds `source` to the `tool_call` trace event. It changes nothing else.
- **Alternatives rejected:** a gateway layer between the runtime and tools (repeats the runtime's checks; see section 2); a class hierarchy of tools (nothing needs it); doing the Agent API as a second HTTP layer (the existing routes are the API).
- **Security, tenancy and privacy:** no new input, store, network call or setting; nothing here is tenant data. The only new data is a source label and a hash of a tool's own definition.

## 6. Work packages
| WP | Work | Exit check |
|---|---|---|
| 1.2 | G1 to G4: `Tool.source`, `Registry.add_tools`, `tool_fingerprint`, registration from every source, `source` in the catalogue and trace | New tests pass; existing suite unchanged and green |
| 1.4 | G5: the conformance suite (this absorbs the old WP 1.3) | Green for the YAML connectors and a second in-test source |
| 1.1 | G6: the Agent API contract, snapshot and test, and the stability rule in the API Design document | Test fails on a removed or retyped field in a contract route |
| 1.5 | Deferred (section 2) | Recorded in the plan's progress table |
| 1.6a | Type the responses of the conversation-time routes (chat, approvals, hand-offs, traces, outbox, tags, transcript, event types) so the stability rule covers them | The snapshot records their response schemas; a test calls each route and checks the answer against its model |
| 1.6b | Type the rest (agents, versions, releases, rollouts, simulations, remaining sessions and events routes) | The same, for the remaining operations |

Order: 1.2, then 1.4, then 1.1, then 1.6a, then 1.6b.
