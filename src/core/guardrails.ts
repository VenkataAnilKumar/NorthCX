import type { LLM, Message } from "./types.js";

export type Verdict = { allow: true } | { allow: false; reason: string };
export interface GuardrailContext { sessionId: string; messages: Message[] }

/** Supervisor layer: inspects proposed tool calls and replies before they take effect. */
export interface Guardrail {
  name: string;
  checkToolCall?(call: { name: string; input: Record<string, unknown> }, ctx: GuardrailContext): Promise<Verdict> | Verdict;
  checkReply?(reply: string, ctx: GuardrailContext): Promise<Verdict> | Verdict;
}

/** Deterministic rule: never emit something that looks like a payment card number. */
export const noCardNumbers = (): Guardrail => ({
  name: "no-card-numbers",
  checkReply: (reply) =>
    /\b(?:\d[ -]?){13,16}\b/.test(reply) ? { allow: false, reason: "Reply contains a card-number-like sequence." } : { allow: true },
});

/** LLM supervisor: a (cheaper) model judges the draft reply against written policies. Fails closed. */
export const llmPolicy = (llm: LLM, policies: string[], model?: string): Guardrail => ({
  name: "llm-policy",
  async checkReply(reply, ctx) {
    const transcript = ctx.messages
      .slice(-8)
      .map((m) => `${m.role}: ${typeof m.content === "string" ? m.content : JSON.stringify(m.content)}`)
      .join("\n");
    const res = await llm.complete({
      model,
      system:
        "You are a compliance supervisor for a customer-service agent. Decide whether the DRAFT reply violates any policy. " +
        'Respond ONLY with JSON: {"allow": boolean, "reason": string}.\nPolicies:\n' +
        policies.map((p, i) => `${i + 1}. ${p}`).join("\n"),
      messages: [{ role: "user", content: `Conversation:\n${transcript}\n\nDRAFT:\n${reply}` }],
      tools: [],
      maxTokens: 200,
    });
    const raw = res.content.map((b) => (b.type === "text" ? b.text : "")).join("");
    try {
      const v = JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1));
      return v.allow ? { allow: true } : { allow: false, reason: String(v.reason ?? "policy violation") };
    } catch {
      return { allow: false, reason: "Supervisor returned unparseable output (fail closed)." };
    }
  },
});
