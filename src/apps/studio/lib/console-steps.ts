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

/** The trace as sentences a CX lead can read. Internal steps (model calls, memory, budgets) are left out; the full trace is still shown beside it. */
export function plainSteps(events: TraceEvent[]): string[] {
  const out: string[] = [];
  for (const e of events) {
    const d = e.data;
    switch (e.type) {
      case "user": out.push(`The customer wrote: ${d.message}`); break;
      case "tool_call": out.push(`Used ${toolLabel(String(d.name))}${pairs(d.input) ? ` (${pairs(d.input)})` : ""}.`); break;
      case "tool_result": out.push(`${toolLabel(String(d.name))} answered: ${clip(pairs(d.output) || JSON.stringify(d.output))}.`); break;
      case "approval": out.push(`Held ${toolLabel(String(d.tool))} for a person: ${d.reason}.`); break;
      case "approval_execution": out.push(`A person decided ${toolLabel(String(d.tool))}: ${d.outcome}.`); break;
      case "guardrail": out.push(`The check ${d.guardrail} stepped in: ${d.reason}.`); break;
      case "handoff": out.push(`Passed to a person: ${d.reason}.`); break;
      case "transfer": out.push(`Passed to the ${d.to} agent: ${d.reason}.`); break;
      case "reply": out.push(`Replied: ${d.reply}`); break;
      case "error": out.push(`Something went wrong: ${d.error}.`); break;
    }
  }
  return out;
}
