# NorthCX Automations: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** Routines staff define that run without a customer message: triggers, steps, approval by a person, and their limits.

## Built
- Routines with manual, schedule, signed webhook and event triggers, and up to ten steps: assistant, report, person, tag, notify, output
- Safety: a person must approve before anything leaves the platform; routines never write to customers; publishing needs a second person; kill switches per routine and for the organization; a daily budget
- Builders: YAML, a canvas, and describe-it (a request in words, checked by the same code)

## Gaps and next steps
- A `tool` step through the tool gateway (write tools need a person step first), `branch` and a bounded `foreach` (design section 8)
- Triggers from connector events
- A scheduled routine that runs the live agent's simulations and alerts (design section 13)

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Automations-Spec.md`](NorthCX_Automations-Spec.md) | Automations and the Builder (master) |
