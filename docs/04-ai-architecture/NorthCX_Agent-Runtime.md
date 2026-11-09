# NorthCX Agent Runtime

Status: **Built**. Updated: 2026-11-09. Master for: the agent run loop, skills, voice, scopes. Describes the runtime as implemented in the Python backend (`src/backend/northcx/runtime.py`, `agent.py`, `guardrails.py`; tests in `src/backend/tests/test_runtime.py` and related files). The TypeScript prototype in `src/prototype` was the first reference implementation of the same semantics; it is kept and tested in CI as a reference, not as the product.

## Concepts
| Concept | Definition |
|---|---|
| Agent | An `Agent` built from a YAML spec or in code: id, instructions, tools, guardrails, model, `max_steps` (`northcx/agent.py`, `spec.py`) |
| Tool | A function with a Pydantic input model, an optional approval rule, a read or write effect and optional scopes |
| Guardrail | Supervisor that checks tool calls and/or replies (`guardrails.py`); input and output checks in `safety/` |
| Session | Message history identified by a session id (`sessionId` in the HTTP API) |
| Run | One user message processed to a final reply |
| Trace | Ordered event log for a run |

## Run loop
1. Load session history, customer facts, context from the company's systems and relevant long-term memories; if a person has the conversation, keep the message for them and stay quiet.
1a. Input checks before the model: personal-data masking, takeover phrasing, abuse and bursts, forced hand-off topics, language detection, budget limits (see Guardrails and Supervisors). A blocked message ends the run with a hand-off.
1b. Append the user message.
2. Build the system prompt: instructions, customer facts, handoff rule.
3. Call the model with tool specs plus the built-in `handoff_to_human` tool.
3a. If the model call fails, the run is escalated and the error is traced.
4. If the model returns text only: run reply guardrails. Allowed, return it and drop any rejected drafts and supervisor feedback from saved history. Rejected, append a supervisor message and retry (max 2 rewrites), then escalate.
5. If the model returns tool calls, for each call in order: record it; handoff ends the run as `escalated` (every `tool_use` in the turn still gets a `tool_result`, so saved history stays valid); unknown tool or invalid input returns an error result; tool guardrails may block; `requiresApproval` stores a pending approval and stops the run as `needs_approval`; otherwise execute and return the result (errors are returned, not thrown).
6. Append tool results and loop. After `max_steps`, escalate.
7. Save history and trace; return a `RunResult` (`reply`, `status`, `trace`, `pending_approvals`, `handoff_id`).

## Statuses
`completed`, `escalated`, `needs_approval`.

## Design rules
- The runtime depends only on the `LLM` interface; a scripted model is used in tests.
- Tool errors never crash a run; the model sees them and can recover.
- Blocking decisions always include a reason that is traced.
- Every exit path saves history and the trace, and saved history is always valid: every `tool_use` is answered and the last turn is the assistant's.
- Guardrail errors count as denials (fail closed); model errors escalate instead of crashing.
- Customer facts are placed in the prompt as untrusted data.
- The agent version that answered is recorded on the trace (null for an agent built from a spec file).

## Notes and known gaps
Notes:
- Approvals are stored (in memory or Postgres) and resumed by `ApprovalFlow` (see the Handoff and Approvals spec). A run started by the platform itself (an approval outcome) uses `trusted=True`: it skips the customer input checks and is traced as a `system` event, but replies and tool calls are still supervised.
- Streaming is supported at the API (`POST /v1/agents/{id}/chat/stream`) and in the widget: the reply is sent after the checks pass, never as unchecked tokens.

Known gaps:
- A blocked tool call is not retried with guidance beyond the error result.
- Tool calls in one turn run one after another, not in parallel.
- Two simultaneous messages in the same conversation can overwrite each other's turn (see Knowledge and Memory).


## Skills, workflow flexibility, brand voice and tool scopes (A3, A4, A10, T6) — as built

**Skills.** A skill is a YAML file: `name`, `instructions`, an ordered list of `steps` (each with a `purpose`, an optional `tool` that completes it, and `required`), and optional extra `tools`. Skills are loaded from `NORTHCX_SKILLS_DIR` (or registered in code) and an agent spec lists the ones it has:

```yaml
skills:
  - {name: refund_flow, flexibility: strict}
  - {name: order_status}          # flexibility defaults to guided
```

The agent's instructions are composed at build time: the spec's own text, then the brand voice, then one section per skill. The tools a skill needs are added to the agent's tools (each once), and a spec that lists a skill whose tool is not registered is refused with every problem listed. `GET /v1/skills` shows what is available.

**Flexibility (A4).** `strict`: the order is enforced. A step's tool is refused until the earlier *required* steps' tools have been used somewhere in the conversation (earlier turns count), and the refusal tells the agent what to do first. `guided`: the agent is told to follow the steps unless the situation calls for something else; nothing is enforced. `free`: the steps are suggestions. Steps without a tool cannot be enforced, only requested.

**Brand voice (A10).** `voice: {tone, guidelines, avoid_phrases, sign_off}`. Tone, guidelines and sign-off are added to the instructions. `avoid_phrases` are also enforced: a reply containing one (whole words, any case) is rejected and the agent is asked to rewrite it.

**Tool scopes (T6).** `tool_scopes: {issue_refund: {requires_customer: true, facts: {tier: [gold, platinum]}, channels: [web, email]}}` limits a tool by who is asking and where: only identified customers, only customers whose fact has one of the listed values (stored facts, plus values from the company's systems when customer context is configured), only on listed channels. Scopes are checked again when an approved action runs, so a customer whose status changed while the approval waited is refused. A tool listed in the spec but not in `tool_scopes` is unrestricted; the agent's `tools` list remains the first limit.

Specs that use none of these keep their digests. These rules complement approvals and the policy library; they do not replace them.

**Pinned skill text.** Referencing a skill by name alone would let someone edit the skill file and change a released agent's behaviour under an unchanged digest, which would break the release gate. So a version carries a copy of every skill it uses (`skill_snapshots`, part of the digest), taken when the version is created and used when the agent is built, whatever the skill file now says. Spec files read at start-up are re-pinned from the current skill files, so editing a skill changes that agent's digest and the gate asks for new proof before the next release.
