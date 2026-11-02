import type { AgentDef, ToolContext } from "./agent.js";
import { toolSpec } from "./agent.js";
import { Trace, TraceStore } from "./trace.js";
import type { MemoryStore } from "./store.js";
import type { Block, LLM, Message, ToolResultBlock } from "./types.js";

export type RunStatus = "completed" | "escalated" | "needs_approval";
export interface RunResult {
  reply: string;
  status: RunStatus;
  traceId: string;
  trace: Trace;
  pendingApprovals: { tool: string; input: unknown; reason: string }[];
}

const HANDOFF = "handoff_to_human";
const MAX_REWRITES = 2;

export class Runtime {
  constructor(private deps: { llm: LLM; store: MemoryStore; traces: TraceStore }) {}

  async run(
    agent: Required<AgentDef>,
    input: { sessionId: string; message: string; customerId?: string },
  ): Promise<RunResult> {
    const { llm, store, traces } = this.deps;
    const trace = new Trace(agent.id, input.sessionId);
    const messages: Message[] = await store.loadMessages(input.sessionId);
    const facts = input.customerId ? await store.getFacts(input.customerId) : {};
    const ctx: ToolContext = { sessionId: input.sessionId, customerId: input.customerId, memory: store };
    const pendingApprovals: RunResult["pendingApprovals"] = [];

    const system =
      agent.instructions +
      (Object.keys(facts).length ? `\n\nKnown customer facts:\n${JSON.stringify(facts)}` : "") +
      `\n\nIf you cannot resolve the issue or the customer asks for a person, call ${HANDOFF}.`;
    const tools = [
      ...agent.tools.map(toolSpec),
      {
        name: HANDOFF,
        description: "Transfer the conversation to a human agent.",
        input_schema: { type: "object", properties: { reason: { type: "string" } }, required: ["reason"] },
      },
    ];

    messages.push({ role: "user", content: input.message });
    trace.add("user", { message: input.message });

    const finish = async (reply: string, status: RunStatus): Promise<RunResult> => {
      trace.add("reply", { reply, status });
      await store.saveMessages(input.sessionId, messages);
      traces.save(trace);
      return { reply, status, traceId: trace.id, trace, pendingApprovals };
    };

    let rewrites = 0;
    for (let step = 0; step < agent.maxSteps; step++) {
      const res = await llm.complete({ model: agent.model || undefined, system, messages, tools });
      trace.add("llm", { step, stopReason: res.stopReason });
      messages.push({ role: "assistant", content: res.content });

      const uses = res.content.filter((b): b is Extract<Block, { type: "tool_use" }> => b.type === "tool_use");

      if (uses.length === 0) {
        const reply = res.content.map((b) => (b.type === "text" ? b.text : "")).join("").trim();
        const verdict = await this.checkReply(agent, reply, input.sessionId, messages, trace);
        if (verdict === null) return finish(reply, "completed");
        if (++rewrites > MAX_REWRITES) {
          return finish("Let me connect you with a teammate who can help.", "escalated");
        }
        messages.push({ role: "user", content: `[supervisor] Your draft was rejected: ${verdict}. Rewrite it.` });
        continue;
      }

      const results: ToolResultBlock[] = [];
      for (const use of uses) {
        trace.add("tool_call", { name: use.name, input: use.input });
        if (use.name === HANDOFF) {
          trace.add("handoff", use.input);
          return finish("I'm connecting you with a teammate who can take it from here.", "escalated");
        }
        const def = agent.tools.find((t) => t.name === use.name);
        if (!def) {
          results.push({ type: "tool_result", tool_use_id: use.id, content: `Unknown tool ${use.name}`, is_error: true });
          continue;
        }
        const parsed = def.input.safeParse(use.input);
        if (!parsed.success) {
          results.push({ type: "tool_result", tool_use_id: use.id, content: `Invalid input: ${parsed.error.message}`, is_error: true });
          continue;
        }
        const blocked = await this.checkTool(agent, use.name, use.input, input.sessionId, messages, trace);
        if (blocked) {
          results.push({ type: "tool_result", tool_use_id: use.id, content: `Blocked by policy: ${blocked}`, is_error: true });
          continue;
        }
        const approval = def.requiresApproval?.(parsed.data);
        if (approval) {
          trace.add("approval", { tool: use.name, reason: approval });
          pendingApprovals.push({ tool: use.name, input: use.input, reason: approval });
          return finish(
            "I've sent this to a teammate for approval and will confirm as soon as it's processed.",
            "needs_approval",
          );
        }
        try {
          const out = await def.run(parsed.data, ctx);
          trace.add("tool_result", { name: use.name, output: out as any });
          results.push({ type: "tool_result", tool_use_id: use.id, content: JSON.stringify(out) });
        } catch (e) {
          trace.add("error", { tool: use.name, error: String(e) });
          results.push({ type: "tool_result", tool_use_id: use.id, content: `Tool error: ${e}`, is_error: true });
        }
      }
      messages.push({ role: "user", content: results });
    }
    return finish("Let me connect you with a teammate who can help.", "escalated");
  }

  private async checkReply(agent: Required<AgentDef>, reply: string, sessionId: string, messages: Message[], trace: Trace) {
    for (const g of agent.guardrails) {
      const v = await g.checkReply?.(reply, { sessionId, messages });
      if (v && !v.allow) { trace.add("guardrail", { guardrail: g.name, reason: v.reason }); return v.reason; }
    }
    return null;
  }

  private async checkTool(agent: Required<AgentDef>, name: string, input: Record<string, unknown>, sessionId: string, messages: Message[], trace: Trace) {
    for (const g of agent.guardrails) {
      const v = await g.checkToolCall?.({ name, input }, { sessionId, messages });
      if (v && !v.allow) { trace.add("guardrail", { guardrail: g.name, reason: v.reason }); return v.reason; }
    }
    return null;
  }
}
