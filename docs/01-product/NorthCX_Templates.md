# NorthCX Templates

Status: **Built**. Updated: 2026-11-09. Master for: the built-in agent templates.

A template is a ready-made agent for a common support need, together with the scenarios that prove it works. Pick one, fill in a few parameters, and you have a valid agent specification and tests instead of a blank page.

## Built-in templates
| Template | For | Needs |
|---|---|---|
| Order status | "Where is my order?" Looks the order up before answering; legal threats and instructions hidden in messages go to a person | an order-lookup tool |
| Returns and refunds | Return questions and refund requests; refunds above your limit wait for a person; safety and legal topics go to a person | order-lookup and refund tools |
| Help-centre answers | Questions answered only from your own documents, with citations; hands off when the documents do not cover it | the knowledge library |
| Triage and hand-off | Collects the details a person needs, then hands over; for teams that want people to resolve everything | nothing |

## Using one
1. List them (`GET /v1/templates`) and read the parameters (company name, return window, which tool to use, and so on). Every parameter has a default.
2. Render it (`POST /v1/templates/{id}/render` with a new agent id and your values). You get the agent specification, its scenarios, and a list of **tools your deployment does not have yet**. Nothing is saved.
3. If tools are missing, add them (a connector file or code) or change the tool parameter to the name you have.
4. Save it as a version (`POST /v1/templates/{id}/create-version`). The version is validated like any hand-written one.
5. Put the scenario file in your scenarios directory and restart, so the release gate has something to check; run the scenarios against the version, then publish through the normal gate and environments.

## Rules
- Parameters are plain one-line text. They fill placeholders and nothing is evaluated, so a value cannot add settings or run anything.
- A template that would produce an invalid agent, or scenarios that would not load, is refused with the reason.
- Teams can add their own templates in `NORTHCX_TEMPLATES_DIR`; reusing a built-in id replaces it.
- Templates give you a sensible start, not a finished product: read the instructions, adjust them to your policies, and keep the scenarios.

## Not built
A gallery in the web console, saving scenarios from the API (they are files today), and templates for voice or for multi-agent set-ups.
