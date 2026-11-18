# NorthCX Model layer: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** Which models agents use and how: the provider interface, local and cloud providers side by side (NorthCX is hybrid, decision 198), fallbacks, budgets, model selection and qualification.

## Built
- A provider interface with a Claude adapter and an OpenAI-compatible adapter; provider-qualified model names
- Retries, fallback models, token budgets and daily budgets in currency; per-tenant model providers (tenancy preview)
- Per-agent qualification: a model serves an agent only after passing that agent's scenarios (recorded from a live simulation run)
- Hybrid model selection across local, private and public tiers, partly built

## Gaps and next steps
- The first local-model pass (for example on Ollama), then cloud-model passes when keys are available; a published list of models that pass the shipped scenarios
- Live mode for configured providers in the command-line simulation runner (today it uses Claude only)
- Prompts tuned per model where needed; a Studio screen for choosing models per tier and seeing qualification
- Routing simple tasks to cheaper models

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Model-Providers.md`](NorthCX_Model-Providers.md) | Model interface and providers (master) |
| [`NorthCX_Hybrid-Model-Selection.md`](NorthCX_Hybrid-Model-Selection.md) | Model selection across tiers |
| [`NorthCX_Local-Models-Guide.md`](NorthCX_Local-Models-Guide.md) | Running local models and qualifying them |
