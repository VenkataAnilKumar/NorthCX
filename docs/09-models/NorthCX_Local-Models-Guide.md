# Running NorthCX with local models

Status: **Partly built**. Updated: 2026-11-18. Master for: how an operator runs NorthCX on local models (self-hosted servers such as Ollama, vLLM, llama.cpp or LM Studio), alone or beside cloud models, and how a local model is qualified for an agent. Written from the code (`northcx/providers/config.py`, `openai_compat.py`, `bootstrap/settings.py`, `providers/qualification.py`); **not yet run end to end against a real local server**. The first local-model pass will confirm or correct it.

NorthCX is hybrid (decision 198): local, private-cloud and public-cloud models can serve agents side by side. How a model is chosen per conversation (data policy, qualification, rules, cost) is in `NorthCX_Hybrid-Model-Selection.md`; providers and budgets are in `NorthCX_Model-Providers.md`.

## 1. What you need
- A machine that can run the model at a useful speed (in practice a GPU for anything beyond small models).
- A local server that speaks the OpenAI chat-completions format. Ollama is the example below; vLLM, llama.cpp and LM Studio work the same way through the same provider type.
- A model that supports **tool calling**. NorthCX agents act through tools, so a model without it cannot serve them. Check the model's own documentation.

## 2. The providers file
Point NorthCX at the server with a providers file (`NORTHCX_PROVIDERS_FILE`, YAML, mounted into the container). With a providers file no Anthropic key is needed.

```yaml
providers:
  - name: local                      # model names become  local:<model>
    type: openai-compatible
    baseUrl: http://ollama:11434/v1  # the local server's OpenAI-compatible address
    allowInsecureHttp: true          # needed for plain http to any host other than localhost; only on a trusted private network
    defaultModel: <model>            # a tool-calling model you have pulled
    default: true                    # bare model names go to this provider
    where: local                     # local | private-cloud | public-cloud
    capabilities: {tools: true, parallelTools: false, images: false, maxContextTokens: 32000}
    prices: {<model>: {inputPerMillion: 0, outputPerMillion: 0, currency: USD}}
```

Notes, from the code:
- **Plain http** is refused unless the address is `localhost`, `127.0.0.1` or `::1`, or `allowInsecureHttp: true` is set. In Docker Compose the server is usually reached by a service name (for example `ollama`), so the flag is needed; set it only on a trusted network.
- **Keys:** a local server usually needs none, so leave out `apiKeyEnv` and `apiKeyFile`. If you set `apiKeyEnv`, that variable must exist or the server refuses to start. A key written in the file is always refused.
- **Capabilities:** declare what the model can really do. `parallelTools: false` is the safer setting for small models until tested.
- **Prices:** give every model a price (0 for a local one). With a daily budget set, the server refuses to start if a default model has no price in the budget currency.
- **Unknown settings** in the file stop the server with a message naming them.

## 3. Local and cloud together
Add a cloud provider (for example `type: anthropic`, named `anthropic`, which needs `ANTHROPIC_API_KEY`, or another `openai-compatible` service with `where: public-cloud`) in the same file. Then decide which conversations may leave your network with routing rules (`NORTHCX_ROUTING_RULES_FILE`): by default sensitive conversations may not use the public cloud, and a conversation with no allowed model goes to a person. See `NorthCX_Hybrid-Model-Selection.md` for the rules and the `model_choice` record in each trace.

## 4. Qualify the model for each agent
A model should serve an agent's customers only after it has passed that agent's required scenarios (decision 164). With the server running on the providers file:

1. Run the agent's scenarios live on the candidate model: `POST /v1/simulations/runs` with `mode: live`, the `agent`, its saved `version`, and `model: local:<model>`. The Studio Simulations page offers live mode when a model is configured.
2. Record the qualification from that run: `POST /v1/agents/{agent}/qualifications` with `model` and `runId`. It holds only for that exact agent definition; changing the prompt or tools needs a new run.
3. List them: `GET /v1/agents/{agent}/qualifications`.

The command-line runner uses the same configured models: with `NORTHCX_PROVIDERS_FILE` set, `python -m northcx.simulation examples/scenarios --specs examples --registry examples.support_agent:registry --model live` runs the scenarios on the default provider (a local one in the example above). Recording a qualification still goes through the server (step 2).

## 5. What to expect
- Small local models are usually close to large cloud models on single, simple tool calls and fall behind on multi-step tool chains, which are common in support work (the research summary is in `NorthCX_Hybrid-Model-Selection.md`, section 6). Qualification is how you find out for your agents; do not assume.
- Prompts, the judge, drafting and analytics were first written for Claude and may need tuning for other models. Use a strong model as the judge; a judge should not grade its own answers.
- Report what you find (which model, which scenarios failed and why) so the list of known-good local models can be published here.

## 6. The first local-model pass (2026-11-22)
Run in the development container (4 CPU cores, 15 GB memory, no GPU). Weights were pulled from Docker Hub's model artifacts (`ai/qwen2.5:3B-Q4_K_M`, checksum verified) because the usual model hosts are blocked there, and served by `llama-cpp-python` 0.3.37 (`--chat_format chatml-function-calling`, 8,192 tokens of context). NorthCX was pointed at it with the providers file that `scripts/setup.py --local-model-url ... --local-model ...` wrote.

| Model | Server | Shipped scenarios (judge checks skipped) | Qualified |
|---|---|---|---|
| Qwen2.5 3B Instruct, Q4_K_M | llama-cpp-python 0.3.37 | 8 of 18 passed; 10 required failed | **No** |

Speed: about 6 tokens a second on this CPU; a short answer takes 5 to 20 seconds. One run, one model, one server: a first data point, not a ranking.

What worked end to end:
- The providers file, the provider and the Models page (the tier now reads `local`; see below), and the health page's Models check.
- A refund over the limit asked for by a customer was held for approval; approving it ran the refund (`state: executed`). A model call that failed was handed to a person (`model_error`) instead of answering.
- Refunds under the limit, forced hand-off topics, prompt-injection and personal-data guardrails before the model, and stale-approval expiry passed.

What did not, and why (all of it the model and its server, not NorthCX's rules):
- **The model often wrote a tool call as text** (`functions.lookup_order:`) instead of making one, so no tool ran and the customer was shown that text. `order-lookup` failed this way, as did the large-refund scenario. A model like this must not be qualified; qualification is what stops it serving customers.
- After an approved refund the model sent an empty reply.
- Scenarios that expect the model to hand over, escalate or trip a guardrail on its own (customer asks for a person, card numbers, repeated rejections) failed because a 3B model did not do it. These need a stronger model.
- Do not use this combination with real customers.

Things found by this pass and fixed in NorthCX:
- llama-cpp-python ignores `tools` unless the request also carries `tool_choice`; NorthCX now sends `tool_choice: "auto"` (the API's default) whenever it sends tools.
- It rejected assistant messages with `content: null`; NorthCX now sends an empty string (the API allows either).
- The Models page showed a local provider as `public-cloud` when no routing rules file was set; it now shows the tier from the providers file.

Notes for operators:
- `scripts/setup.py` writes `maxContextTokens: 32000`; set it to the context your server really runs (here 8,192), or a long conversation will fail at the server.
- Use a different, stronger model as the judge, and judge checks were skipped here: judging with the same 3B model would grade its own answers.
- Larger models (7B and up) and Ollama or vLLM servers have not been tried. Attempting to build llama.cpp's own `llama-server` here was not allowed, so that server was not tested; its native tool-call handling may behave differently.

## 7. Not yet done
- A pass with a model that can be expected to qualify (7B or larger) and a stronger judge, and a list of local models known to pass the shipped scenarios.
- Calibrating the judge against people's labels (needs a model good enough to judge).
- The pass on Ollama, vLLM and llama.cpp's own server.
