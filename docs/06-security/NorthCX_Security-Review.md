# NorthCX security review (Phase 6)

Status: **Reference**. Updated: 2026-11-09. Master for: the Phase 6 security review (done by the authors, not independent).

Scope: the backend, web console, browser SDK and deployment files at the commit that adds this file. Done by the authors; see the threat model for what was considered and what remains.

## What was done

| Activity | Result |
|---|---|
| Static analysis of the backend (bandit) | 0 high; 3 medium (one deliberate bind to all interfaces inside the container, two SQL builders that only paste constant text, both now covered by a test); 4 low (swallowed errors in best-effort paths such as a listener that must never break a conversation) reviewed and accepted |
| Dependency audit | `pip-audit`: no known vulnerabilities; `npm audit` for the web console and SDK: none |
| Access control sweep | every `/v1` route has a permission; unlisted routes and unknown methods are refused; role-exact test for all seven roles; customer-token test for the five routes a customer may use (existing tests, re-run) |
| Route fuzzing | 2,920 requests with junk path values and bodies against every `/v1` route with an admin key: no server errors |
| Parser fuzzing | random and hostile input to the file sniffer, ID-token verifier, journey and assist parsers, language detector, speech cleaner: found one bug (below) |
| Manual review | authentication (keys, tokens, SSO, voice stream), outbound calls, file handling, SQL, regular expressions, response headers, browser output sinks, CORS, secrets in logs and audit, redirect handling, deployment defaults |
| Browser checks | full console and widget runs in a real browser, including cross-origin chat, sign-in through a local identity provider, hand-off and teammate reply |

## Findings and what was done

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | No global limit on request body size: any endpoint would read an arbitrarily large body into memory | Medium (denial of service) | **Fixed**: per-endpoint caps (1 MB default, 11 MB uploads, 4 MB knowledge documents) enforced before parsing, by declared length or as the body arrives; tests |
| 2 | Voice stream had no per-connection message limit; a bridge or an attacker holding a channel key could trigger unlimited model calls | Medium | **Fixed**: message bucket (100/s, burst 300) closes the connection; 120 spoken turns a minute per key |
| 3 | No default security headers on API or console responses | Low | **Fixed**: `nosniff`, `no-referrer`, frame denial, permissions policy, `no-store` for API answers; Studio sends a CSP that forbids framing, plugins, base changes |
| 4 | ID-token verifier raised an unhandled error when the token header or body was valid JSON but not an object (a 500 on the sign-in callback, not a bypass) | Low | **Fixed**; parser fuzz test added |
| 5 | The outbox webhook client relied on the library default not to follow redirects | Low | **Fixed**: made explicit; a test now fails if any client is created without it |
| 6 | Per-address rate limits behind a proxy apply to the proxy's address unless uvicorn is told which proxies to trust | Medium (operational) | **Documented** in the deployment guide and threat model |
| 7 | A 20,000-character text attachment takes about a second to scan for personal data (quadratic pattern on dot-heavy input) | Low | **Accepted**: bounded by the attachment size cap and upload rate limit |
| 8 | Roles are server-wide and every `traces:read` role sees conversation text | Medium (privacy) | **Accepted**, documented; per-agent scoping is future work |

## Tests added to keep it that way

`tests/test_hardening.py` (size caps, headers, flood), `tests/test_security_review.py` (no pasted SQL, no dangerous constructs, no client following redirects, CORS never echoing `null` or lookalike origins, no secrets in audit or errors, hashed keys, customer tokens refused by staff routes, parser fuzz).

## Before exposing a deployment to the internet

- Commission an independent penetration test (not done).
- Terminate TLS at a proxy, set `FORWARDED_ALLOW_IPS`, apply shared rate limits there, keep the database off public networks (the compose file already does).
- Use SSO for people and short-lived, narrowly used API keys for machines; issue the fewest admin keys.
- Install from the hash-pinned lock files and re-run the audits on every release.
- Decide per agent whether to accept pictures and PDFs, and whether callers' numbers may be trusted.
- Legal review for call recording and for the countries your customers are in.

## Since this review
- Backend dependencies are hash-pinned (`requirements.lock`, `requirements-dev.lock`) and audited in CI (`pip-audit`).
- Rate limits and daily budgets can be shared across processes (`NORTHCX_LIMITS_BACKEND=postgres`), and background jobs run under database leases.
- PDFs can reach the model as masked text (`pdf_text`); pictures still reach it unmasked.
- The review has not been repeated for the work added since (the provider registry, the webhook test sender, several-process operation, the unfinished Workspace and Admin web code). Repeat it, and the independent penetration test, before 1.0.0.

## Reporting a problem

See `SECURITY.md` in the repository root.
