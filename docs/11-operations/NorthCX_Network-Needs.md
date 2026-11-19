# Network needs

What a NorthCX server must be able to reach, so a network team can write an egress allow-list, and where each address is set. Everything not listed here is not contacted. Status: written from the code on 2026-11-19; the lists are checked against the residency report by `test_the_network_page_lists_every_destination_the_report_can_show`; not yet checked on a locked-down network.

Rules that hold for every destination below: https only (http is accepted for `localhost`, and for a model on a trusted private network when its provider says `allowInsecureHttp`), redirects are never followed, and the server's own address checks run before any request. The same list, with the region of each address, is `GET /v1/residency` and Studio's Data residency screen.

## Always
| Destination | Setting | Notes |
|---|---|---|
| PostgreSQL | `NORTHCX_DATABASE_URL` (and `NORTHCX_MIGRATION_DATABASE_URL` for upgrades) | Usually inside your network. Holds everything NorthCX stores |

## Models
| Destination | Setting | Notes |
|---|---|---|
| Claude | `ANTHROPIC_API_KEY`; `ANTHROPIC_BASE_URL` | Default `api.anthropic.com`. Not contacted without a key |
| Each model service you list | `NORTHCX_PROVIDERS_FILE` (`baseUrl` of each provider) | A local or private-cloud model is a destination too, so it appears in the report |
| Embeddings | `NORTHCX_EMBEDDINGS_URL` | Meaning-based knowledge search |
| Speech to text | `NORTHCX_TRANSCRIBE_URL` | Recordings uploaded to build agents |

## Customers and staff
| Destination | Setting | Notes |
|---|---|---|
| SMS | `NORTHCX_SMS_NUMBER` | `api.twilio.com` |
| Telegram | `NORTHCX_TELEGRAM_TOKEN` (`NORTHCX_TELEGRAM_API_URL`) | `api.telegram.org` |
| WhatsApp | `NORTHCX_WHATSAPP_PHONE_ID` (`NORTHCX_WHATSAPP_API_URL`) | `graph.facebook.com` |
| Email | `NORTHCX_SMTP_URL` | Your mail server |
| Helpdesk | `NORTHCX_CHATWOOT_URL`, `NORTHCX_INBOX_WEBHOOK_URL` | Hand-off packages |
| Single sign-on | `NORTHCX_SSO_ISSUER` | Staff sign-in only |
| Customer context | `NORTHCX_CONTEXT_URL` | Customer identifier |
| Attachment scanning | `NORTHCX_ATTACHMENT_SCAN_URL` | Files customers upload |

## Notices and traces
| Destination | Setting |
|---|---|
| Reply and status webhook | `NORTHCX_WEBHOOK_URL` |
| Status event webhook | `NORTHCX_EVENTS_WEBHOOK_URL` |
| Alert webhook | `NORTHCX_ALERT_WEBHOOK_URL` |
| Routine results | `NORTHCX_AUTOMATION_DESTINATIONS` (a `mailto:` destination goes through the SMTP server above) |
| Langfuse | `NORTHCX_LANGFUSE_URL` |
| OpenTelemetry | `NORTHCX_OTLP_ENDPOINT` |

## Tools
Only hosts the operator names are reachable; a tool or connection cannot add one.
| Destination | Setting |
|---|---|
| Business systems (YAML connectors) | `NORTHCX_CONNECTOR_HOSTS` |
| MCP servers | `NORTHCX_MCP_HOSTS` |

## Not in the residency report
- Websites the knowledge crawler reads (`NORTHCX_CRAWL_HOSTS`): they receive no customer data. Nobody can crawl a host that is not listed.
- Inbound calls (channel webhooks, the widget, the API) are not egress; they are covered in the Deployment Guide.
