import type { LLM, Message } from "./types.js";

export type Verdict = { allow: true } | { allow: false; reason: string };
export interface GuardrailContext { sessionId: string; messages: Message[] }

/** Supervisor layer: inspects proposed tool calls and replies before they take effect. */
export interface Guardrail {
  name: string;
  checkToolCall?(call: { name: string; input: Record<string, unknown> }, ctx: GuardrailContext): Promise<Verdict> | Verdict;
  checkReply?(reply: string, ctx: GuardrailContext): Promise<Verdict> | Verdict;
}

const luhn = (digits: string) => {
  let sum = 0;
  for (let i = 0; i < digits.length; i++) {
    let d = Number(digits[digits.length - 1 - i]);
    if (i % 2 === 1) { d *= 2; if (d > 9) d -= 9; }
    sum += d;
  }
  return sum % 10 === 0;
};

/** Deterministic rule: never emit a valid payment-card number (13-19 digits passing the Luhn check). */
export const noCardNumbers = (): Guardrail => ({
  name: "no-card-numbers",
  checkReply: (reply) => {
    for (const m of reply.matchAll(/\b\d(?:[ -]?\d){12,18}\b/g)) {
      const digits = m[0].replace(/\D/g, "");
      if (digits.length >= 13 && digits.length <= 19 && luhn(digits)) {
        return { allow: false, reason: "Reply contains a payment-card number." };
      }
    }
    return { allow: true };
  },
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
