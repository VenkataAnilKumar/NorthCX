# NorthCX Session Prompts

Status: **Reference**. Updated: 2026-11-18. Master for: ready-to-use prompts for Claude Code sessions that carry out the priorities in `../05-technical/NorthCX_Agent-Platform-Design.md` (section 13). Each prompt is one step; run them in order. Replace `[ref]` with the path to the reference folder (`northcx-sources`, kept outside this repository).

## Shared header (paste before every prompt)
```text
Read CLAUDE.md and docs/05-technical/NorthCX_Agent-Platform-Design.md (sections 1a, 13
and the section for this step). Reference projects are read-only in [ref]; never commit them.

Do NOT run the full backend or web test suites. Run only tests for code you touch and
the new tests you write. If a targeted test fails, say whether it is your change or looks
pre-existing, and ask before fixing anything unrelated.
Method: read the relevant code, write a short plan, show it and wait for my go-ahead.
Then work in small steps on a new branch from main.
Rules: no copied third-party code; git commit -s; update affected docs, CHANGELOG.md and
.env.example; route-permission entries for new endpoints; approvals, scopes, dry-run,
secrets and audit on every tool path; mark anything that needs a live model as unverified.
Do not open a pull request or merge. At the end list the tests you ran and did not run.
```

## 1. Live-model pass (only when an Anthropic API key is available)
```text
With ANTHROPIC_API_KEY set: run the example agent in the Studio test console; run the
shipped scenarios in live mode (python -m northcx.simulation); try an agent draft, a journey
draft, a plain-language analytics question and the judge. Record every difference from the
scripted results in docs/08-implementation/NorthCX_Release-Checklist.md and fix or document
each. Do not tick checklist items without evidence.
```

## 2a. Tool gateway
```text
Design section 5. Add a ToolSource interface that wraps the YAML connectors in
src/backend/northcx/connectors.py and produces normal Tool objects. Add a conformance suite
every source must pass: read tools run; write tools are held or dry-run in simulation;
secrets never appear in results; redirects and disallowed hosts are refused. Existing
connector tests must pass unchanged. No MCP yet.
```

## 2b. MCP client
```text
Design section 5. Read the MCP 2026-07-28 spec in [ref] first and report anything that
contradicts the design. Add an MCP source behind ToolSource using the official MCP Python
SDK. Default every tool to write unless the operator trusts the server's read-only hint; pin
and hash each server's tool list and require re-approval on change; screen tool output as
untrusted. Add operator-only, tenant-scoped connections and a catalogue of tools and
triggers. Test with a fake MCP server and prompt-injection scenarios.
```

## 2c. First connectors: Zendesk, Shopify, Stripe
```text
Using the gateway, add connections for Zendesk, Shopify and Stripe: a vendor-hosted MCP
server where one exists and is documented, otherwise a YAML connector. Write tools
(refunds, ticket updates, order changes) need approval by default. Test with recorded fake
responses only; mark each connector "needs a sandbox account to verify" in the docs. List
the exact sandbox accounts the owner must create.
```

## 3a. Guided Studio for non-engineers
```text
Design section 7. Build the guided path, not the graph editor: start from a template or
pasted procedures; a plain-language summary of what the agent will do, which tools it may
use and what needs approval; validation messages in the author's terms; write tools needing
approval by default; test in place with the trace shown as steps in words and one-click
"make this a test". YAML moves behind an Advanced view. The spec stays the source of truth.
Read the Studio AGENTS.md and the Next.js docs in node_modules first; use [ref]/studio/sim
for layout ideas only. Add browser and accessibility tests in the existing style.
Write the script for the usability gate (a CX lead releases a template agent unaided).
```

## 3b. Shadow mode
```text
Add shadow mode for an agent and environment: the agent produces each reply and any tool
calls, but nothing is sent or executed until a person approves or edits it in the Workspace
inbox; read tools may run. Reuse the approval and outbox paths in approval_flow.py rather
than a new mechanism. Record approve, edit and reject as quality signals. Customers see
nothing different except response time. Add tests that nothing reaches a customer or an
external system without a person.
```

## 4. Operator experience
```text
For self-hosted operators: a one-command install with a setup wizard (database password, API
key, demo or live model, allowed hosts); an upgrade path tested from the previous release
with migrations; backup and restore commands for Postgres and stored files; and a health page
showing database, migrations, model reachability, channels and alert delivery. Update the
deployment guide and owner runbooks. Do not weaken any existing start-up check.
```

## 5a. Firm resolution figure
```text
In src/backend/northcx/insights.py the resolution rate is provisional and can overstate
resolution because a customer's return in a new conversation is not detected. Link
conversations to a customer reference where one is known, count a return within the window
as not resolved, and show both the old and new figure with their denominators. Update the
metric definitions in the docs and propose a written definition of "resolved" for the owner
to approve.
```

## 5b. Plain-language quality criteria
```text
Next to the deterministic rubric in src/backend/northcx/qa.py, let an author write criteria
in plain language (for example "never promise a refund date"). They are judged by the model on
masked transcripts, stored apart from people's reviews, respect the daily budget and are
always shown as model judgements. The deterministic rubric stays the baseline. Mark the
quality of judgements as unverified until the live-model pass.
```

## Later (not prompted yet)
The graph editor for Studio, the AG-UI endpoint and assistant-ui, Automations `tool` and `branch` steps, NorthCX as an MCP server, and a local-model design. See design sections 6 to 8.
