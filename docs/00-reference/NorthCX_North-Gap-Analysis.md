# NorthCX → North for CX: Gap Analysis & Build Plan

Status: **Reference**. Updated: 2026-11-09. Master for: the 2026-11-04 gap analysis against an external product. Lives in `00-reference/` because it compares NorthCX with an external product (Cohere North) and names third-party systems.

A snapshot of 2026-11-04. The response to it is `../08-implementation/NorthCX_Gap-Closure-Plan.md` and, for the staff side, the design of 2026-11-09 (`../07-design/NorthCX_Platform-Features-and-Tabs.md`: the Workspace, Pilot, Agent Hub, Automations and the Admin app). Based on the NorthCX repository, which its README describes as 1.0.0-rc.1, with more than 1,300 backend tests, Studio, the SDK and widget, six channels, approvals, simulations and releases.

The key difference from Cohere North is the user. **NorthCX is customer-facing**: AI agents talk to your customers. **North is employee-facing**: a private AI workspace for staff, with chat, search, agents, automations, apps, and deployment anywhere. So "NorthCX like North" means keeping the strong customer-agent engine and adding the staff-side workspace plus North's enterprise platform layers.

## North module vs. NorthCX today

| North module | NorthCX status | What to build |
|---|---|---|
| **Agents** | ✅ Strong: YAML agents, typed tools, specialists, journeys, templates, drafting an agent from procedures or recordings | Agents for **staff**, not only customers: a "CX Copilot" for support reps, team leads, QA and ops |
| **Automations** | ⚠️ Partial: the only user-defined schedule is knowledge re-crawls (alerts, retention, approval expiry and exports already run in the background) | A natural-language automation builder with triggers (schedule, webhook, ticket created), multi-step background jobs and run history. Examples: daily ticket triage, nightly QA sampling, auto-tagging, SLA breach sweeps, weekly voice-of-customer reports |
| **Skills** | ✅ Built: skill files with enforced step order | A skill catalog shared across agents, with versions, owners and usage counts |
| **Libraries** | ⚠️ Knowledge base only (customer-facing answers) | Shared team libraries for prompts, macros, playbooks, response templates and files, with sharing permissions |
| **Applications** (decks, dashboards, docs from chat) | ❌ Missing | Generate outputs from chat: CX reports, QBR decks, dashboards, CSV exports, ticket-trend briefs |
| **Memory** | ✅ Customer memory, recall and erase | Staff and team memory: a rep's preferences, ongoing case context, team norms |
| **Guardrails** | ✅ Very strong, better than most | Extend the same controls to the staff workspace: what staff may ask, data loss prevention on exports, approved models per role |
| **Admin** | ⚠️ Roles, keys with a role and expiry (not yet limited to agents), OpenID Connect SSO, hash-chained audit log, residency | SAML SSO, automatic user provisioning (SCIM), groups, keys scoped to specific agents, per-team budgets, an agent catalog with approval to publish |
| **Discover** (enterprise search) | ⚠️ Search over imported or crawled knowledge only | Permission-aware search across CX systems (tickets, CRM, call transcripts, Confluence/Notion, Slack/Teams) for staff questions like "why are refunds up this week?" |
| **Insights** | ✅ Plain-language analytics with real denominators | Cross-source insights joining conversations with CRM, revenue and churn, plus scheduled insight digests |

## Platform layers to add

### 1. Staff-facing CX workspace (the biggest gap)
- A chat home for support reps and leads: ask questions, search, run agents and automations
- A copilot inside the helpdesk: ticket summaries, suggested replies, next steps, policy lookup (H6 assist exists for hand-offs; generalize it)
- QA reviewer workspace: auto-score 100% of conversations, coaching notes
- Team lead and VP of CX workspace: trends, root causes, generated reports and decks
- Surfaces: browser extension, Slack and Teams bot, and sidebars for Zendesk, Salesforce and Intercom

### 2. Model layer
- Today it is Claude only (by design, behind one interface). Build the planned multi-provider layer (`04-ai-architecture/NorthCX_Model-Providers.md`): an adapter that works with OpenAI-style APIs and self-hosted models, provider-qualified model names, fallback chains that mix providers
- Private inference option: self-hosted open-weight models for air-gapped customers
- Cost governance: budgets in currency (only token budgets exist today), per-team spend dashboards, routing simple tasks to cheaper models

### 3. Connectors (today: five generic YAML starting points)
- Native connectors: Zendesk, Salesforce Service Cloud, Intercom, Freshdesk, HubSpot, Shopify, Stripe, Gorgias, Jira, Confluence, Notion, Google Drive, SharePoint, Slack, Teams
- An MCP client so tools can come from any MCP server, plus an MCP server so other tools can reach NorthCX
- A connector SDK and an OAuth app setup flow in Studio

### 4. Deployment (North's main selling point)
- Today: Docker Compose, one company and one region per deployment
- Add, in order: **multi-tenant managed cloud** (P10, planned), then **dedicated single-tenant**, then **customer cloud account (VPC)** via Helm, Kubernetes and Terraform for AWS, Azure and GCP, then **on-premises or air-gapped**
- Upgrade tooling, license keys, and an ops console for health, versions and backups

### 5. Commercial platform
- Usage metering and outcome-based billing (P11, planned); "resolved" needs an agreed definition first
- Internal back office: tenants, plans, feature flags, support access
- Developer portal: API reference (the API exists, publish it), SDK docs, a sandbox tenant, a webhook tester
- Native iOS and Android SDKs (only the web SDK is built)

### 6. Trust and compliance
- The independent penetration test and a run against a live model (both open items in the README)
- SOC 2 Type II, ISO 27001, ISO 42001, GDPR documentation; HIPAA for healthcare CX
- Customer-managed encryption keys, a public trust center site
- Fix the known limits: per-process rate limits, unmasked images and PDFs sent to the model, unlocked dependencies (since fixed in Wave 0: shared limits, PDFs as masked text, hash-pinned dependencies; pictures still reach the model unmasked)

### 7. Marketing site and positioning
- Landing page: "North for Customer Experience: private, supervised AI agents for customers and the teams who serve them" (a working phrase from this analysis only; it borrows another product's name and must not be used outside this folder; NorthCX's own positioning is in the Product Definition)
- Solution pages by CX function (support, contact center, QA, CX ops) and industry (retail, fintech, telecom, travel)
- Deployment options page, security page, demo booking

## Suggested build order

| Stage | Build |
|---|---|
| **Now (finish 1.0)** | Penetration test, live-model pass, judge calibration, the known-limit fixes |
| **MVP of "North for CX"** | Managed multi-tenant cloud, staff chat workspace with search over knowledge plus tickets, rep copilot in Zendesk and Salesforce, three native connectors, SAML and SCIM, metering |
| **Seed** | Automations builder, team libraries, generated reports and decks, Slack and Teams bot, MCP, cost governance, SOC 2 |
| **Series A** | VPC deployment (Helm/Terraform), multi-provider models, developer portal, agent catalog with publishing approval, outcome-based billing |
| **Series B+** | On-prem and air-gapped deployment, private models, native mobile SDKs, a marketplace for connectors and templates, ISO 42001 and HIPAA, global data residency |

The safety and release machinery (approvals, simulations, release gates, audit) is ahead of most platforms. The gaps are the employee workspace, enterprise connectors, multi-tenancy and billing, and flexible deployment.

## Sources
- NorthCX repository: README, CHANGELOG, `03-specs/NorthCX_Feature-Catalog.md`, `04-ai-architecture/NorthCX_Model-Providers.md`, `08-implementation/NorthCX_Roadmap.md`, `01-product/NorthCX_Pricing-Model.md`, `05-technical/NorthCX_Integrations.md`
- [Cohere North](https://cohere.com/north)
- Editable copy: [Claude Doc](https://claude.ai/artifact/Knd2TEjCDth8DhgGQninMr)
