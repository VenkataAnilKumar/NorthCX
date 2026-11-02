import type { TraceEvent } from "@/lib/api";

const labels: Record<string, string> = {
  user: "Customer message", llm: "Model call", tool_call: "Tool call", tool_result: "Tool result",
  guardrail: "Guardrail", approval: "Approval requested", handoff: "Handoff", reply: "Reply", error: "Error",
};
const tone: Record<string, string> = {
  guardrail: "border-[var(--warn)]", approval: "border-[var(--info)]", handoff: "border-[var(--warn)]", error: "border-[var(--bad)]",
  reply: "border-[var(--ok)]",
};

function summary(e: TraceEvent): string {
  const d = e.data;
  switch (e.type) {
    case "user": return String(d.message ?? "");
    case "tool_call": return `${d.name}(${JSON.stringify(d.input)})`;
    case "tool_result": return `${d.name} → ${JSON.stringify(d.output)}`;
    case "guardrail": return `${d.guardrail}: ${d.reason}`;
    case "approval": return `${d.tool}: ${d.reason}`;
    case "handoff": return String(d.reason ?? "");
    case "reply": return `${d.reply} (${d.status})`;
    case "error": return String(d.error ?? "");
    case "llm": return `step ${d.step} · ${d.stop_reason}`;
    default: return JSON.stringify(d);
  }
}

export function TraceTimeline({ events }: { events: TraceEvent[] }) {
  const start = events[0]?.t ?? 0;
  return (
    <ol className="space-y-2" aria-label="Trace events">
      {events.map((e, i) => (
        <li key={i} className={`rounded-lg border-l-4 bg-surface p-3 text-sm shadow-sm ${tone[e.type] ?? "border-border"}`}>
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium">{labels[e.type] ?? e.type}</span>
            <span className="text-xs text-muted">+{Math.round((e.t - start) * 1000)} ms</span>
          </div>
          <p className="mt-1 break-words text-muted">{summary(e)}</p>
        </li>
      ))}
    </ol>
  );
}
