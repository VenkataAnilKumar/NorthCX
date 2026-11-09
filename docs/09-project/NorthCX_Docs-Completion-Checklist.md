# NorthCX documentation completion checklist

Status: **Plan**. Updated: 2026-11-09. Master for: what the documents cover and what is open. Tracks whether the product documents cover the full designed platform before implementation starts. "Done" means the document describes the Workspace, Pilot, Agent Hub, Builder, Automations, personal intelligence, hybrid models and the Admin regrouping, with states marked designed or built honestly.

**End-to-end review (2026-11-09):** every active document was read in full and corrected against the code and decisions 1 to 172: out-of-date facts, features called planned that are built, tables and routes that do not exist, superseded duplicates, unverified claims (for example fact provenance, linting in CI), guessed pronouns and named external products. Commits "Docs review: ..." on `main`.

| Area | Document | State |
|---|---|---|
| Vision, scope, pillars | `01-product/NorthCX_Product-Definition.md` | Done (section 3a) |
| Requirements | `01-product/NorthCX_PRD.md` (FR35 to FR41) | Done |
| Overview | `01-product/NorthCX_Product-Overview.md`, `README.md` | Done |
| Personas | `01-product/NorthCX_Personas.md` (Tess added) | Done |
| Success metrics | `01-product/NorthCX_Success-Metrics.md` (staff platform proposals) | Done; baselines need a pilot |
| Pricing | `01-product/NorthCX_Pricing-Model.md` | **Blocked on D1** (open versus commercial); not changed |
| Market | `02-market/NorthCX_Competitive-Analysis.md`, `00-reference/` | Existing; refresh after D1 |
| Catalog | `03-specs/NorthCX_Feature-Catalog.md` (106 for 1.0, 103 built; section 12: 77 designed) | Done |
| Specifications | Workspace, Pilot, Personal-Intelligence, Automations specs; Agent Hub design | Done (drafts) |
| Stories and journeys | `03-specs/NorthCX_User-Stories.md` (US45 to US61), `NorthCX_User-Journey.md` (J11 to J15) | Done |
| Non-functional | `03-specs/NorthCX_Non-Functional-Requirements.md` | Done (proposals) |
| AI architecture | `04-ai-architecture/` Hybrid-Model-Selection, Model-Providers | Done; Knowledge-and-Memory and Guardrails need a staff-memory section when E5.5 is scheduled |
| Technical architecture | `05-technical/NorthCX_Staff-Platform-Architecture.md` | Done (proposed) |
| Database and API | `NorthCX_Database-Schema.md`, `NorthCX_API-Design.md` | Proposed tables and routes are in the architecture document; these two are updated when each migration or route lands (the sync tests require it) |
| Security | Threat model and Security-and-Compliance (staff platform sections) | Done |
| Design | UI-UX-Design-Proposal (approved look, navigation modes, tab icons), Platform-Features-and-Tabs, Admin-Platform-Design, Agent-Hub-Design, Design-System, Studio (with the former Studio-UI-Spec), 59 mockups | Done |
| Plan | Implementation-Plan, Gap-Closure-Plan, Roadmap, Project-Status (finished 1.0 plans are in `99-archive/`) | Done; plan epics already cover E1 to E22 |
| Testing | `08-implementation/NorthCX_Testing-Strategy.md` | Done |
| Glossary and decisions | Glossary; Decision-Log to #161 | Done |

## Owner decisions still open (they do not block implementation of the first slice)
1. ~~Tabs and first-release set~~ Decided (decision 162).
2. ~~Pilot decisions~~ Decided (decision 163).
3. ~~Profile~~ Decided (decision 166).
4. ~~Models~~ Decided (decision 164).
5. ~~Agent Hub~~ Decided (decision 165).
6. ~~Builder~~ Decided (decision 165).
7. ~~Automations~~ Decided (decision 165).
8. ~~Organization page list (25 pages)~~ Decided (decision 167).
9. ~~Platform~~ Decided in part (decision 170): D2 working name and D3 to D9 accepted; **D1 (open versus commercial) stays open** and still blocks pricing.

## Not documented because it is not yet known
Real customer evidence, pricing, a pilot baseline for any metric, an independent security test, a live-model quality pass.
