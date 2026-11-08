# NorthCX Model Providers

## Today
NorthCX talks to Claude through Anthropic's official SDK. This is a deliberate first step: it gives correct handling of the API (authentication, streaming formats, error types, new model features) with the least code to own.

The SDK is **isolated behind one interface**. The runtime, supervisors, simulations, summarisation, judge and every other part depend only on `LLM.complete(LLMRequest) -> LLMResponse` (`northcx/types.py`). The only module that imports the SDK is `northcx/providers/anthropic.py` (`AnthropicLLM`, re-exported from `northcx/llm.py`); a test fails if any other module does. Retries, fallback models, timeouts, circuit breaking and budgets (`ReliableLLM`, `UsageLedger`) wrap any backend, so they work unchanged for any provider added later.

## The provider layer (built, 1.1 work in progress)
`northcx/providers/` holds the shared types and the registry:
- **`Provider`** (`base.py`): `name`, `default_model`, `capabilities` (tools, parallel tools, images, documents, context size), `prices` (per million tokens, supplied by the operator, never guessed) and `complete`. Errors are `ProviderError` with a `status_code` (plus `ProviderTimeout` and `ProviderUnreachable`, which `is_transient` already treats as retryable); messages never contain keys or request bodies.
- **`ProviderRegistry`** (`registry.py`): implements the same `LLM` interface, so it drops in wherever a model backend is used (including `ReliableLLM`). Models are named `provider:model`; a name whose prefix is not a registered provider is a bare model name and goes to the default provider (so existing agents and `llama3:8b`-style names are unchanged). `require_tools` refuses an agent with tools on a model that cannot call them.
- **Claude, two clients** (`anthropic.py`): the SDK (default) and a direct HTTPS client (`NORTHCX_ANTHROPIC_CLIENT=http`). One conformance test file runs both: plain reply with usage and the answering model, tool call, tool-result round trip, no tools sent when none are declared, status codes and transient classification, timeouts, key placement.
Not built yet: other providers (OpenAI-compatible next), the providers file, fallback chains across providers with capability checks at release time, currency budgets. See the Implementation Plan, E1.

## Later: our own multi-provider layer
The plan is to replace the SDK with NorthCX's own provider layer and add other providers, behind the same interface:

1. **Direct Claude client** (built as an option). Call the Claude Messages API over HTTPS ourselves (the request and response shapes are already what the runtime uses), keeping the SDK only until parity is proven by the existing test suite and a live comparison.
2. **Provider adapters.** One small adapter per provider (for example an OpenAI-compatible one that also covers many self-hosted models). Each translates between NorthCX's neutral request and the provider's format.
3. **Neutral message format.** Messages and tool calls currently use Claude's block shapes (`text`, `tool_use`, `tool_result`). When a second provider arrives, that shape stays as NorthCX's own neutral format and each adapter translates at its edge; the runtime does not change.
4. **Per-agent and per-purpose model choice.** An agent already names a model (`model`), and summaries and the judge accept their own. With several providers a model name will be qualified by provider (`anthropic:claude-...`), and the fallback chain may mix providers.
5. **Capabilities.** Providers differ in tool calling, parallel calls, token reporting, context size and cost. Each adapter will declare what it supports so the platform can refuse a configuration that cannot work (for example an agent that needs tools on a model that has none) instead of failing in a conversation.

## Rules for adapters
- Return `usage` (input and output tokens) so budgets work, and report the model that actually answered.
- Raise errors that carry an HTTP-style `status_code` where the provider has one, so retry and fallback decisions stay correct (`is_transient`).
- Never put credentials in errors, traces or logs; read them through the secret store.
- Pass the same conformance tests as `AnthropicLLM`: plain reply, tool call, tool result round trip, error mapping, usage.
