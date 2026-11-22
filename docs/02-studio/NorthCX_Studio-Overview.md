# NorthCX Agent Studio: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** Where agents are built, tested and released: the admin console (Studio), its design, templates and the Agent Hub.

## Built
- Studio console (port 3001) with agents, editor (form and YAML), journeys, templates, Agent Hub, simulations, versions and releases, approvals, hand-offs, insights, monitoring, knowledge, policies, models and budgets, channels, memory, privacy, trust and organization settings
- Drafting an agent or a journey from procedures, transcripts or recordings; an "Improve this agent" loop that proposes and tests but never releases
- Organization policies and templates with a two-person rule; signed built-in templates

## Gaps and next steps
Phase 4 is designed in [`NorthCX_Guided-Studio.md`](NorthCX_Guided-Studio.md) (requirements R1 to R11, the order of work); nothing in it is built.

- A guided path for non-engineers: template, connect, preview, test, release, with checks in plain words (design sections 7 and 13)
- A graph editor kept equivalent to the YAML by round-trip tests; a connector picker; an agent catalogue with publish approval; a side-by-side view of live and candidate versions
- The usability gate: a CX lead releases a template agent unaided

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

Interfaces worth studying for each NorthCX screen (named, so kept in `00-reference`): [`../00-reference/NorthCX_Agent-UI-References.md`](../00-reference/NorthCX_Agent-UI-References.md).

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Studio.md`](NorthCX_Studio.md) | Studio as built (master) |
| [`NorthCX_Platform-Features-and-Tabs.md`](NorthCX_Platform-Features-and-Tabs.md) | Tabs, names and features of both apps |
| [`NorthCX_Admin-Platform-Design.md`](NorthCX_Admin-Platform-Design.md) | Admin screens |
| [`NorthCX_Agent-Hub-Design.md`](NorthCX_Agent-Hub-Design.md) | Agent Hub |
| [`NorthCX_UI-UX-Design-Proposal.md`](NorthCX_UI-UX-Design-Proposal.md) | Visual and interaction design |
| [`NorthCX_Design-System.md`](NorthCX_Design-System.md) | Design system |
| [`NorthCX_Templates.md`](NorthCX_Templates.md) | Built-in agent templates |
| [`mockups/`](mockups/) | HTML mockups |
