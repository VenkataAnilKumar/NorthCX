import type { VersionDiff } from "@northcx/api-client";

export function DiffView({ d }: { d: VersionDiff }) {
  if (d.identical) return <p className="text-sm text-muted">No differences.</p>;
  const groups: [string, { added: string[]; removed: string[]; changed?: string[] }][] = [
    ["Tools", d.tools], ["Reply guardrails", d.guardrails], ["Input guardrails", d.input_guardrails], ["Always-to-a-person topics", d.forced_handoff]];
  return (
    <div className="space-y-3 text-sm">
      {d.instructions && <pre aria-label="Instructions diff" className="overflow-x-auto rounded-lg bg-bg p-3 text-xs">{d.instructions}</pre>}
      {groups.filter(([, g]) => g.added.length || g.removed.length || g.changed?.length).map(([name, g]) => (
        <p key={name}><span className="font-medium">{name}:</span>{" "}
          {g.added.map((x) => <span key={x} className="mr-2 text-[var(--ok)]">+ {x}</span>)}
          {g.removed.map((x) => <span key={x} className="mr-2 text-[var(--bad)]">− {x}</span>)}
          {g.changed?.map((x) => <span key={x} className="mr-2 text-[var(--warn)]">~ {x}</span>)}</p>
      ))}
      {Object.entries(d.other).map(([k, v]) => <p key={k}><span className="font-medium">{k}:</span> {JSON.stringify(v.from)} → {JSON.stringify(v.to)}</p>)}
    </div>
  );
}
