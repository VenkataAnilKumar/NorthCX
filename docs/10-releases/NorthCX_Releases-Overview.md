# NorthCX Release management: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** How agent versions reach customers safely, and how NorthCX itself is released.

## Built
- Immutable agent versions; environments (dev, staging, production); a publish checklist and a release gate tied to the exact version
- Staged rollouts with comparison, promote or stop; one-step rollback

## Gaps and next steps
- A side-by-side view of live and candidate versions in Studio; an agent catalogue with publish approval
- Cutting NorthCX 1.0: the items in the release checklist that need the owner or an outside party

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Release-Management.md`](NorthCX_Release-Management.md) | Versions, environments, rollout and rollback (master) |
| [`NorthCX_Release-Checklist.md`](NorthCX_Release-Checklist.md) | Finishing NorthCX 1.0 |
