import Anthropic from "@anthropic-ai/sdk";
import type { LLM, LLMRequest, LLMResponse } from "./types.js";

export const DEFAULT_MODEL = "claude-sonnet-5-5";

/** Claude backend using the official Anthropic SDK. */
export class AnthropicLLM implements LLM {
  private client: Anthropic;
  constructor(private opts: { apiKey?: string; model?: string } = {}) {
    this.client = new Anthropic({ apiKey: opts.apiKey });
  }
  async complete(req: LLMRequest): Promise<LLMResponse> {
    const res = await this.client.messages.create({
      model: req.model ?? this.opts.model ?? DEFAULT_MODEL,
      max_tokens: req.maxTokens ?? 1024,
      system: req.system,
      messages: req.messages as any,
      ...(req.tools.length ? { tools: req.tools as any } : {}),
    });
    return { content: res.content as any, stopReason: res.stop_reason ?? "end_turn" };
  }
}

type Script = LLMResponse | ((req: LLMRequest) => LLMResponse);

/** Deterministic fake model for tests and simulations. */
export class ScriptedLLM implements LLM {
  requests: LLMRequest[] = [];
  constructor(private script: Script[]) {}
  async complete(req: LLMRequest): Promise<LLMResponse> {
    this.requests.push(req);
    const next = this.script.shift();
    if (!next) throw new Error("ScriptedLLM: script exhausted");
    return typeof next === "function" ? next(req) : next;
  }
}

export const text = (t: string): LLMResponse => ({ content: [{ type: "text", text: t }], stopReason: "end_turn" });
export const toolCall = (name: string, input: Record<string, unknown>, id = `tu_${Math.random().toString(36).slice(2, 8)}`): LLMResponse => ({
  content: [{ type: "tool_use", id, name, input }],
  stopReason: "tool_use",
});
