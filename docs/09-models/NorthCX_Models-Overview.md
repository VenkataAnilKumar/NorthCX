# NorthCX Model layer: Overview

Status: **Reference**. Updated: 2026-11-18. Master for: the one-page overview of this area: what it covers, what is built, the gaps, and where each topic is documented. Details live in the documents it links to; where they disagree, they win.

**What this area covers.** Which models agents use and how: the provider interface, providers, fallbacks, budgets and model selection.

## Built
- A provider interface with a Claude adapter and an OpenAI-compatible adapter; provider-qualified model names
- Retries, fallback models and token budgets; per-tenant model providers (tenancy preview)
- Hybrid model selection across local, private and public tiers, partly built

## Gaps and next steps
- A short design for local and private models for self-hosted buyers, without promising equal quality (design section 13)
- Budgets in currency; routing simple tasks to cheaper models
- The live-model pass

Plan: [`Agent Platform design`](../00-platform/NorthCX_Agent-Platform-Design.md) (phasing in section 10, priorities in section 13). States come from the documents below and the changelog, not from running the product.

## Documents in this folder
| Document | What it is |
|---|---|
| [`NorthCX_Model-Providers.md`](NorthCX_Model-Providers.md) | Model interface and providers (master) |
| [`NorthCX_Hybrid-Model-Selection.md`](NorthCX_Hybrid-Model-Selection.md) | Model selection across tiers |
