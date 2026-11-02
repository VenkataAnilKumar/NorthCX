import { appendFileSync, mkdirSync } from "node:fs";
import { randomUUID } from "node:crypto";

export type TraceEventType = "user" | "llm" | "tool_call" | "tool_result" | "guardrail" | "approval" | "handoff" | "reply" | "error";
export interface TraceEvent { t: number; type: TraceEventType; data: Record<string, unknown> }

export class Trace {
  readonly id = randomUUID();
  readonly events: TraceEvent[] = [];
  constructor(readonly agentId: string, readonly sessionId: string) {}
  add(type: TraceEventType, data: Record<string, unknown> = {}) {
    this.events.push({ t: Date.now(), type, data });
  }
  toolsCalled(): string[] {
    return this.events.filter((e) => e.type === "tool_call").map((e) => String(e.data.name));
  }
}

export class TraceStore {
  private traces = new Map<string, Trace>();
  constructor(private dir?: string) {
    if (dir) mkdirSync(dir, { recursive: true });
  }
  save(trace: Trace) {
    this.traces.set(trace.id, trace);
    if (this.dir) appendFileSync(`${this.dir}/traces.jsonl`, JSON.stringify(trace) + "\n");
  }
  get(id: string) { return this.traces.get(id); }
  list(sessionId?: string) {
    return [...this.traces.values()].filter((t) => !sessionId || t.sessionId === sessionId);
  }
}
