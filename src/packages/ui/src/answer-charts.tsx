import { formatTime } from "@northcx/api-client";

export interface SeriesPoint { start: number; value: number | null }

/** A line chart with a table behind it, so the figures are readable without seeing the picture. */
export function LineChart({ label, points, bucket }: { label: string; points: SeriesPoint[]; bucket: "hour" | "day" }) {
  const vals = points.map((p) => p.value ?? 0);
  const max = Math.max(1e-9, ...vals);
  const w = 320, h = 90, pad = 6;
  const x = (i: number) => pad + (i / Math.max(1, points.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - (v / max) * (h - 2 * pad);
  const path = vals.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const fmt = (t: number) => new Date(t * 1000).toLocaleString(undefined, bucket === "hour" ? { hour: "2-digit", day: "numeric", month: "short" } : { day: "numeric", month: "short" });
  return (
    <figure className="mt-3">
      <figcaption className="text-xs text-muted">{label}, by {bucket} (highest {Number.isInteger(max) ? max : max.toFixed(2)})</figcaption>
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`${label} by ${bucket}: ${vals.length} points, highest ${max}`} className="mt-1 h-24 w-full max-w-md">
        <line x1={pad} x2={w - pad} y1={h - pad} y2={h - pad} stroke="var(--border)" />
        <path d={path} fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinejoin="round" />
        {vals.length <= 40 && vals.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r="2.5" fill="var(--primary)" />)}
      </svg>
      <details className="mt-1 text-xs text-muted"><summary className="cursor-pointer">Show as a table</summary>
        <table className="mt-1"><tbody>{points.map((p) => <tr key={p.start}><td className="pr-4">{fmt(p.start)}</td><td className="tabular-nums">{p.value ?? "–"}</td></tr>)}</tbody></table></details>
    </figure>
  );
}

/** Ranked bars: each row has its number written out, so colour is never the only signal. */
export function BarList({ label, rows }: { label: string; rows: { name: string; count: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <figure className="mt-3">
      <figcaption className="text-xs text-muted">{label}</figcaption>
      <ul className="mt-1 max-w-md space-y-1 text-sm">{rows.slice(0, 12).map((r) => (
        <li key={r.name}><div className="flex justify-between gap-3"><span className="truncate">{r.name}</span><span className="tabular-nums text-muted">{r.count}</span></div>
          <div className="h-2 rounded bg-border/50" aria-hidden="true"><div className="h-2 rounded bg-primary" style={{ width: `${(r.count / max) * 100}%` }} /></div></li>))}</ul>
    </figure>
  );
}

export function ConversationList({ rows }: { rows: { sessionId: string; firstMessage: string; lastStatus: string; language: string | null; handedOff: boolean; rating: number | null; endedAt: number }[] }) {
  return (
    <ul className="mt-3 space-y-2 text-sm">{rows.map((c) => (
      <li key={c.sessionId} className="rounded-lg border border-border p-2">
        <a className="font-medium text-primary underline" href={`/conversations/${encodeURIComponent(c.sessionId)}`}>{c.firstMessage || "(no text)"}</a>
        <p className="text-xs text-muted">{c.lastStatus.replace("_", " ")}{c.handedOff ? " · reached a person" : ""}{c.language ? ` · ${c.language}` : ""}{c.rating ? ` · rated ${c.rating}` : ""} · {formatTime(c.endedAt)}</p>
      </li>))}</ul>
  );
}
