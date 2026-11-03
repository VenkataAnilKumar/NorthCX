# NorthCX Studio UI Spec

Status: Draft. Phase 4.

## Purpose
Let CX teams create and tune agents without code, producing the same agent definition used by developers.

## Screens
| Screen | Function |
|---|---|
| Agents | List, create, version, publish |
| Agent editor | Instructions, tools toggles, guardrail policies, approval rules |
| Test console | Chat with a draft agent and see the live trace |
| Simulations | Run scenarios, see pass/fail, diff against last release |
| Conversations | Search runs, open traces, mark failures |
| Approvals | Pending actions with payload; approve or reject |
| Insights | Resolution, escalation, guardrail hits, cost |
| Settings | Keys, roles, channels, retention |

## Current state
Built in `src/web`: Access and audit page (keys, audit log, integrity check), identity display and role-aware buttons and forms, overview, versions and releases page per agent (save a version from an editable spec, run its scenarios, gate, publish, diff, roll back, history), simulations page (release gate, run, results), handoff queue with package view and resolve, test console with live trace (U2), conversations with trace viewer (U4, without tagging), approvals queue (U5, decision only), agents (read-only view), settings. Not built: agent editor (U1), scenario editing (U3), knowledge (U6), publish (U7), role-based views (U8).

## Screen detail
- **Agent editor (U1):** instructions with policy sections, tool toggles with approval rules, guardrail and forced-handoff lists, model settings, skills and journeys (Phase 4), template picker.
- **Test console (U2):** chat with a draft, live trace beside the conversation, replay a past conversation against the draft.
- **Simulations (U3):** suites, required flags, results with diffs against the last release, create a scenario from a conversation.
- **Review (U4, built):** queue with reasons, transcript, right/wrong, hand-off needed, failure kinds, note, scenario draft; quality cards on Insights.
- **Conversations (U4):** filters, tags, failure causes, open trace, create regression scenario.
- **Approvals (U5):** queue with age and risk, payload, context, approve/reject with note.
- **Knowledge (U6):** sources, freshness, test queries with citations.
- **Publish (U7):** change summary, diff, required checks, environment, rollout percentage, rollback.
- **Role-based views (U8):** CX, developer, reviewer, compliance, admin.

## Principles
Every edit is versioned and revertible; publish requires passing required simulations; traces are one click from any conversation.

## Open
Visual flow editor vs instruction-first editing; build vs adopt (Build-vs-Adopt).
