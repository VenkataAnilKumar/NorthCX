# NorthCX performance and cost

Status: measured on one small machine with an offline stand-in for the model. Treat the numbers as the platform's own overhead, to size and compare, and measure again on your hardware with your model before committing to a capacity.

## The two tools

```bash
# How many conversations can a server hold, and how fast does it answer?
python -m northcx.loadtest --url https://api.example.com --key <channel key> --users 200 --conversations 2000 --max-p95-ms 4000
python -m northcx.loadtest --users 300 --conversations 900 --think-ms 1000 --model-ms 800     # in this process, pretending the model takes 800 ms

# What does a conversation cost in model tokens?
python -m northcx.cost scenarios/ --specs agents/ --registry yourmodule:registry --price-in <per million> --price-out <per million> --conversations-per-day 2000
python -m northcx.cost scenarios/ --specs agents/ --registry yourmodule:registry --baseline baseline.json --max-increase 20   # fail CI if a change makes conversations dearer
```

`loadtest` simulates customers who get a chat token, chat for a few turns with pauses (order questions, small talk, a request for a person), rate the conversation, and report throughput, errors by status, reply-time percentiles per kind of request, event-loop lag and memory. `--max-p95-ms` and `--max-error-rate` make it exit 1 so it can gate a release. `cost` runs your scenarios with their scripted model and counts what the model would be sent on every call (instructions, tool descriptions and the whole conversation so far, which is re-sent each time) and what it answered; prices are yours, nothing in NorthCX knows a provider's price list.

## Measurements (4 cores, 16 GB, Postgres 16 on the same machine, Python 3.13, offline demo model)

The load generator ran on the same machine, so it took CPU from the server; real capacity on dedicated hardware is somewhat higher.

| Setup | Result |
|---|---|
| Server in memory (no database), no pauses, 25 / 100 / 300 customers | 600 / 560 / 520 requests per second; chat reply p50 37 ms / 167 ms / 538 ms (all waiting for the one process) |
| Same, with 300 customers, 1 s pauses and a pretended 800 ms model | 136 requests per second, chat p50 983 ms, p95 1.86 s: the model's 800 ms plus about 180 ms; event loop never behind (lag p95 under 2 ms) |
| One server process with Postgres, 30 customers with 300 ms pauses | 62 requests per second, chat p50 258 ms, p95 441 ms, no errors |
| One server process with Postgres, 100 customers, no pauses (saturated) | about 74 requests per second (roughly 50 conversation turns per second); chat p50 1.8 s, p95 3.6 s, no errors |
| Two server processes sharing the database, 50 customers each | 153 requests per second together (2.0x one process), chat p50 about 0.9 s |
| One turn, one customer at a time, Postgres | about 20 ms (it was 25 ms before the database-call reductions below); in memory about 2 ms |
| Memory | about 63 MB at start, growing a few MB per thousand conversations in memory mode (state lives in the database otherwise) |

What that means for sizing:

- A turn costs the platform about 20 ms of one core's time with Postgres. Almost all of the wait in a real conversation is the model (typically seconds), so a process holds many more simultaneous conversations than it can finish turns per second: 300 customers talking with 1 s pauses and an 800 ms model used a tenth of the in-memory capacity.
- Plan capacity in **turns per second per process: about 50 with Postgres** on this hardware. Peak turns per second is roughly peak simultaneous customers divided by the average time between their messages (reading time, typing time, and the model's reply time).
- Add processes to scale out; the application is stateless and they share the database (measured: two processes gave twice the throughput). Postgres was not the limit in these runs.
- Limits are per process by default (with N processes the real limit is N times the setting); `NORTHCX_LIMITS_BACKEND=postgres` shares them. Measured on the same machine over loopback: about 3 ms per check one at a time and about 600 checks per second with 20 keys in flight, so it adds one small database write to each limited request (negligible next to a model call, visible on very cheap endpoints). Many requests on one key take turns on that key's row.

## Where the time goes and what was done about it

A chat turn made 63 database statements, 37 of them only `BEGIN` and `ROLLBACK` housekeeping, and rewrote the whole conversation each time. After this work it makes about 26 meaningful statements: reads no longer open transactions, the pool no longer rolls back connections that are already clean, a turn writes only the messages that are new (so long conversations no longer cost more to save), and a trace's events go in with one statement. What remains is spread thinly across many small lookups (live version, rollout, route, hand-off hold check, customer facts, memory recall); none dominates. The database connection pool now defaults to 20 connections per process (`NORTHCX_DB_POOL_SIZE`) instead of SQLAlchemy's 5.

Another finding from the test: keys with the `channel` role (your servers minting chat tokens, telephony bridges) shared the 600-requests-a-minute default of every other key, so a site starting more than 10 chats a second was throttled at the token step. Channel keys now default to 6,000 a minute (`NORTHCX_CHANNEL_RATE_LIMIT_PER_MINUTE`).

## Cost of a conversation

Measured on the example support agent's scripted scenarios (characters / 4, an estimate good to roughly 25% for English):

- A scenario that calls the model makes about 1.8 calls on average and sends about 690 input tokens and receives about 40 output tokens. The agent's instructions and tool descriptions alone are about 320-390 tokens, re-sent on every call.
- A conversation that takes more calls costs more than the sum of its parts because the whole history goes again each call: the longest example (3 calls) sends about 3x the tokens of its first call.
- At illustrative prices of 3 in / 15 out per million tokens that is about 0.003 per conversation, or about 160 a month at 2,000 conversations a day. A real model writes longer answers and real conversations are longer, so use these as a floor for comparing versions, not as a quote. Run `northcx.cost` on scenarios that look like your traffic and keep a baseline in CI.

How to keep it down: shorten instructions and tool descriptions (they are the fixed part), keep conversations to the point, use skills and journeys rather than long free text, summarise long histories (`NORTHCX_SUMMARIZE_AFTER_TOKENS`), cap each day (`NORTHCX_DAILY_TOKEN_BUDGET`), and consider your provider's prompt caching, which lowers the real cost of the repeated part and is not modelled here.

## What was not measured

- A real model (no key in the test environment): reply times with your model are its latency plus about 20 ms.
- Voice, attachments and large knowledge bases under load.
- Long runs: no soak test beyond minutes, so memory growth over days is unmeasured.
- A Postgres on another machine: add the network round trip, about 25 statements per turn, to each turn (0.5 ms of network latency adds about 12 ms).
