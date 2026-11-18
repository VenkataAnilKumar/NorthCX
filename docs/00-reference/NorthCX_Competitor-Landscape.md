# NorthCX Competitor Landscape

Status: **Reference**. Updated: 2026-11-18. Master for: the named competitors of NorthCX, grouped, with what each group is strong at and how NorthCX answers it. It lives in `00-reference/` because it names other companies' products; the neutral analysis and the plan for each loss scenario are in `../00-platform/NorthCX_Competitive-Analysis.md` (sections 4 and 9).

Facts come from vendor pages, third-party comparisons and reviews found by web search in November 2026. They are directional: pricing in particular is mostly unpublished and reported second-hand, and nothing here was tested hands-on.

## Groups
| Group | Products | Strength | NorthCX's answer |
|---|---|---|---|
| Enterprise CX agent platforms | Sierra, Decagon | Plain-language procedures compiled to structured logic (Sierra Journeys, Decagon Agent Operating Procedures), simulations before launch, always-on quality monitoring, voice; outcome-based pricing (Sierra reported from about $150,000 a year, unconfirmed) | The same teach, test, deploy, improve loop, self-hosted and inspectable; supervision and audit as the edge |
| Helpdesk-native AI | Intercom Fin, Zendesk AI agents, Salesforce Agentforce, Freshdesk Freddy, HubSpot, Gorgias | They are the system of record, so data is there without setup; fast deployment; Intercom Fin is the most often recommended all-rounder (one source: about $0.99 per outcome) | Native connectors and shadow mode beside the existing setup; no lock-in to one helpdesk; per-action approvals and a release gate |
| No-code CX automation | Ada | Built for non-engineers; multilingual | Guided Studio for non-engineers is the response; ready-made agents with tests |
| Contact centre and voice | Cognigy (part of NiCE), Kore.ai, Parloa, PolyAI | Enterprise voice and contact-centre depth | Not competed on yet: a reference setup on the voice bridge instead |
| Open-source and builders | Botpress, Rasa; general agent builders such as Dify, Langflow and Sim | Flexible, low cost | CX-specific: supervision, simulations, release gates and audit are built in, not assembled |

## Product practices worth matching (from these competitors)
- Plain-language procedures generated from existing procedures or transcripts (Sierra, Decagon, Intercom).
- Simulations on past conversations before launch, and on a schedule or in CI with alerts (Intercom, Decagon).
- Quality criteria written in plain language and checked on live conversations (Decagon Watchtower).
- Tone and rules per customer segment or product line (Intercom Fin Guidance).
- A feed of suggested improvements (Intercom Fin Suggestions, Sierra monitors).

Where these are planned in NorthCX: `../00-platform/NorthCX_Agent-Platform-Design.md` (section 2b and section 13). The research behind them: `NorthCX_Agent-Platform-Research.md`.

## Weaknesses reported by reviewers (unverified)
- Individual decisions are hard to understand in real time (reported for Decagon).
- Limited control over simulations (reported for Intercom Fin).
- Long deployments for the contact-centre platforms (one competitor's estimate: three to six months for Cognigy and Kore.ai).
