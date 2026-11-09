# NorthCX Studio UI Spec

> **Archived 2026-11-09.** Merged into `../07-design/NorthCX_Studio.md`. Kept for history; not maintained.

> **Note (2026-11-09):** this describes the Studio on `main` (flat navigation). The planned grouped Admin app, the Workspace and the shared design system are specified in `NorthCX_Platform-Features-and-Tabs.md`, `NorthCX_Admin-Platform-Design.md` and `NorthCX_Design-System.md`. Names there win where they differ.

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
Built in `src/apps/studio`: Access and audit page (keys, audit log, integrity check), identity display and role-aware buttons and forms, overview, versions and releases page per agent (save a version from an editable spec, run its scenarios, gate, publish, diff, roll back, history), simulations page (release gate, run, results), handoff queue with package view and resolve, test console with live trace (U2), conversations with trace viewer (U4, without tagging), approvals queue (U5, decision only), agents (read-only view), settings. Not built: agent editor (U1), scenario editing (U3), knowledge (U6), publish (U7), role-based views (U8).

## Screen detail
- **Agent editor (U1):** instructions with policy sections, tool toggles with approval rules, guardrail and forced-handoff lists, model settings, skills and journeys (Phase 4), template picker.
- **Test console (U2):** chat with a draft, live trace beside the conversation, replay a past conversation against the draft.
- **Simulations (U3):** suites, required flags, results with diffs against the last release, create a scenario from a conversation.
- **Review (U4, built):** queue with reasons, transcript, right/wrong, hand-off needed, failure kinds, note, scenario draft; quality cards on Insights.
- **Conversations (U4):** filters, tags, failure causes, open trace, create regression scenario.
- **Approvals (U5):** queue with age and risk, payload, context, approve/reject with note.
- **Knowledge (U6):** sources, freshness, test queries with citations.
- **Customer widget (C7, built):** `<northcx-chat>`, documented in `05-technical/NorthCX_Client-SDK.md`.
- **Attachments (C10, built):** a paperclip in the test console; the trace shows what was attached.
- **Specialist agents (R8, built):** a section in the editor to choose which agents this one may pass conversations to and when; the trace shows each transfer.
- **Monitoring (built):** active alerts, rules, recent alert events with delivery status and a test-alert button, and the conversations flagged by the always-on checks with filters and links to traces.
- **Hand-off collaboration (H6/H7, built):** suggested help, a reply box and a hand-back checkbox on each open hand-off.
- **Journeys (A5/A6, built):** editor section to write or draft a journey, tie steps to tools, choose strictness, and create test scenarios; Insights show journeys reached and completed.
- **Single sign-on (P5, built):** a 'Sign in with single sign-on' button on Settings when configured, a landing page that stores the session, and Sign out.
- **Staged rollout (Q11, built):** panel on the agent page to start, change the share, compare current and candidate, promote or stop.
- **Publish (U7, built):** the versions page shows each version's checklist and disables Publish until the blocking checks pass.
- **Publish (U7):** change summary, diff, required checks, environment, rollout percentage, rollback.
- **Role-based views (U8):** CX, developer, reviewer, compliance, admin.

## Principles
Every edit is versioned and revertible; publish requires passing required simulations; traces are one click from any conversation.

## Open
Visual flow editor vs instruction-first editing; build vs adopt (Build-vs-Adopt).
