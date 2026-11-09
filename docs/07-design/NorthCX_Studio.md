# NorthCX Studio

Status: **Built**. Updated: 2026-11-09. Master for: the Studio on main today.

Studio is the part of the console where someone who does not write code changes an agent safely. It is built in steps; the first is the agent editor.

## Agent editor (U1) — as built
Open an agent, choose **Edit in Studio**. The form starts from what is live in production and covers everything an agent file can say:
- **Instructions** in plain language, with a character count.
- **Model and limits**: model, most steps per message, token limit per message.
- **Tools**: tick the ones the agent may use. Each shows whether it only reads or changes things, and whether it can need approval.
- **Checks**: reply and tool checks (the policy library, with its settings editable as JSON), customer-message checks, tool-result checks.
- **Always send to a person**: topics with the patterns that trigger them and an optional message to the customer.
- **Brand voice**: tone, guidelines, words to avoid (enforced), sign-off.
- **Skills**: tick a skill and choose strict, guided or free.
- **Style per channel**: optional wording for sms, email, web.

**Live checks.** After each change (a short pause), the page asks the server to check the agent without saving it. The side panel shows "The agent is valid" or every problem found (unknown tool, a check with a missing setting, a topic without a name), what differs from production, and whether it is already the latest saved version. Save is disabled until the agent is valid and different.

**Save and try.** *Save as new version* stores a version; nothing goes live. *Try it in dev* releases that version to the dev environment (no proof needed there) and opens the test console on dev, so the editor can talk to the change straight away. The link to the versions page is where required scenarios are run and the version is published through the release gate and environments, as always.

**Roles.** People who can create versions (developers and above) can edit; others can read the form but not change it.

## Scenario editor (U3) — as built
Simulations lists every scenario with its source (file or saved) and a **New scenario** button. The editor describes a test in plain terms: name, agent, what it checks, whether it is required to release, tags; the **conversation** (what the customer says and, after each message, the agent's expected status, tools called, and words the reply must or must not contain); checks across the whole conversation (tools never called, most model calls, text that must never reach the model); and the **model script** (the answers replayed in offline runs, as replies or tool calls with JSON input). A side panel checks the scenario live and says exactly what is wrong. **Save** stores it; **Run it now (offline)** runs just this scenario and shows pass or fail with the reasons; **Edit as text** shows the scenario as JSON or YAML for anything the form does not cover. A scenario can be drafted from a real conversation (`GET /v1/sessions/{id}/scenario-draft`) and saved here.

Rules that keep the release gate honest:
- Saved scenarios live in the database next to the scenario files. A file scenario wins on a name clash and cannot be changed in the editor.
- Editing a scenario changes its digest, so earlier passes no longer count and the gate asks for a new run. Renaming is not allowed (save under the new name, delete the old).
- Developers can write ordinary scenarios. Deciding which scenarios are **required** (creating, changing, relaxing or deleting one) needs the release permission, because that decides what may be released. Every change is audited.
- An agent made from a template can save the template's tests with it (`saveScenarios`); a developer's copies are optional until a release manager marks them required.

## Knowledge screens (U6) — as built
The Knowledge page manages the documents agents answer from:
- **Sources**: create one (for example "Help centre") with an optional "out of date after N days"; delete one with all its documents.
- **Documents**: a table of title, source, number of passages and when each was last reviewed, with an "out of date" badge, a source filter and an "out of date only" filter. **Add document** takes a title, optional link, and text or Markdown, typed, pasted or loaded from a file (up to 500,000 characters); headings split it into passages. **Edit** opens the original text, and saving replaces the old passages. "Mark as reviewed today" resets the document's freshness clock without changing the text.
- **Try a question**: type what a customer might ask and see the passages the agent would find, numbered the way answers cite them, with their section, date and an out-of-date flag. "Nothing relevant was found" tells you a customer asking this would get no answer from the documents.
Changing knowledge can also re-run tagged scenarios (see the regression settings). Reading needs `knowledge:read`; changing needs `knowledge:write` (developers and admins). Not built: web page crawling, PDF and Word files, and per-document history.

## Planned next
 (documents, freshness), conversation review with failure tagging, a publish checklist that shows the required checks in one place, and single sign-on. The editor does not yet offer an undo history beyond the saved versions and their diffs.

## Design rules
- Studio never bypasses the platform's controls: it creates versions, and publishing still needs the release gate; production releases still need the release permission.
- Everything Studio does is something the API can do, and is audited the same way.
- Words, not file formats: labels describe what a setting does in the customer's terms.

## Screens of the 1.0 Studio (formerly NorthCX_Studio-UI-Spec.md)
### Purpose
Let CX teams create and tune agents without code, producing the same agent definition used by developers.

### Screens
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

### Current state
Built in `src/apps/studio`: Access and audit page (keys, audit log, integrity check), identity display and role-aware buttons and forms, overview, versions and releases page per agent (save a version from an editable spec, run its scenarios, gate, publish, diff, roll back, history), simulations page (release gate, run, results), handoff queue with package view and resolve, test console with live trace (U2), conversations with trace viewer (U4, without tagging), approvals queue (U5, decision only), agents (read-only view), settings. Not built: agent editor (U1), scenario editing (U3), knowledge (U6), publish (U7), role-based views (U8).

### Screen detail
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

### Principles
Every edit is versioned and revertible; publish requires passing required simulations; traces are one click from any conversation.

### Open
Visual flow editor vs instruction-first editing; build vs adopt (Build-vs-Adopt).

