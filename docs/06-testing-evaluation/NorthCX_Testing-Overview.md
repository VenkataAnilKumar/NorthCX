# NorthCX Testing and evaluation: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** How agent changes are proven before customers see them, and how the product itself is tested.

## Built
- Scenario simulations with assertions, simulated customers with personas, attack scenarios, a judge model, regression scenarios from real conversations
- The release gate tied to the exact version; scenarios gate the build in CI
- Load and cost tools; the standing security tests

## Gaps and next steps
- A pass against a live model, and judge calibration (both need an API key)
- Scheduled production simulation runs with alerts; quality criteria written in plain language (design section 13)

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Simulation-and-Evals.md`](NorthCX_Simulation-and-Evals.md) | Simulations, scenarios, judge and the release gate (master) |
| [`NorthCX_Testing-Strategy.md`](NorthCX_Testing-Strategy.md) | How the product is tested |
