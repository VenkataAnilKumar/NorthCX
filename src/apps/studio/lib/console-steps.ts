import type { TraceEvent } from "@northcx/api-client";

export interface ToolCardData { label: string; input: string; outcome: "done" | "held" | "unfinished"; detail: string }

const SHORT = 140;
const clip = (s: string) => (s.length > SHORT ? `${s.slice(0, SHORT)}…` : s);
const pairs = (v: unknown) => (v && typeof v === "object" && Object.keys(v).length
  ? Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k} ${typeof x === "string" ? x : JSON.stringify(x)}`).join(", ") : "");

/** A tool name as words: `lookup_order` is "lookup order"; an MCP tool `shop__orders_lookup` is "orders lookup from shop". */
export function toolLabel(name: string): string {
  const [connection, rest] = name.includes("__") ? name.split("__", 2) : [null, name];
  const words = rest.replace(/_/g, " ");
  return connection ? `${words} from ${connection}` : words;
}

/** The cards for one turn: each tool the agent used, what it asked, what came back, and whether it was held for a person. */
export function toolCards(events: TraceEvent[]): ToolCardData[] {
  const cards: (ToolCardData & { name: string })[] = [];
  for (const e of events) {
    const d = e.data;
    if (e.type === "tool_call") cards.push({ name: String(d.name), label: toolLabel(String(d.name)), input: pairs(d.input) || "no inputs", outcome: "unfinished", detail: "" });
    else if (e.type === "tool_result") {
      const c = [...cards].reverse().find((x) => x.name === d.name && x.outcome === "unfinished");
      if (c) { c.outcome = "done"; c.detail = clip(pairs(d.output) || JSON.stringify(d.output)); }
    } else if (e.type === "approval") {
      const c = [...cards].reverse().find((x) => x.name === d.tool && x.outcome === "unfinished");
      if (c) { c.outcome = "held"; c.detail = String(d.reason ?? ""); }
    }
  }
  return cards.map(({ name: _n, ...card }) => card);
}

/** One event as a sentence a CX lead can read, or null for internal events (model calls, memory, budgets). */
export function plainStep(e: TraceEvent): string | null {
  const d = e.data;
  switch (e.type) {
    case "user": return `The customer wrote: ${d.message}`;
    case "system": return `The platform noted: ${d.message}`;
    case "tool_call": return `Used ${toolLabel(String(d.name))}${pairs(d.input) ? ` (${pairs(d.input)})` : ""}.`;
    case "tool_result": return `${toolLabel(String(d.name))} answered: ${clip(pairs(d.output) || JSON.stringify(d.output))}.`;
    case "approval": return `Held ${toolLabel(String(d.tool))} for a person: ${d.reason}.`;
    case "approval_execution": return `A person decided ${toolLabel(String(d.tool))}: ${d.outcome}.`;
    case "guardrail": return `The check ${d.guardrail} stepped in: ${d.reason}.`;
    case "handoff": return `Passed to a person: ${d.reason}.`;
    case "transfer": return `Passed to the ${d.to} agent: ${d.reason}.`;
    case "reply": return `Replied: ${d.reply}`;
    case "error": return `Something went wrong: ${d.error}.`;
    default: return null;
  }
}

/** The trace as sentences. The full trace is still shown beside it. */
export function plainSteps(events: TraceEvent[]): string[] {
  return events.map(plainStep).filter((x): x is string => x !== null);
}
