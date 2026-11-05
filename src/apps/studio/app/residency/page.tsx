"use client";
import { getResidency, type ResidencyFlow, useLoad } from "@northcx/api-client";
import { ErrorBox, Loading, PageHeader } from "@northcx/ui";

const LABEL: Record<ResidencyFlow["status"], { text: string; cls: string }> = {
  ok: { text: "Allowed", cls: "text-[var(--good)]" },
  not_allowed: { text: "Region not allowed", cls: "text-[var(--bad)]" },
  unmapped: { text: "Region not declared", cls: "text-[var(--warn)]" },
  unchecked: { text: "Not checked", cls: "text-muted" },
};

export default function Residency() {
  const { data, error, loading, reload } = useLoad(getResidency, []);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <>
      <PageHeader title="Data residency" subtitle="Where this server keeps data and every place it sends data to, checked against the residency file." />
      {!data.configured ? (
        <p className="mb-4 rounded-xl border border-border bg-surface p-3 text-sm">No residency file is set, so destinations are listed but not checked. Set <code>NORTHCX_RESIDENCY_FILE</code> (see the Deployment Guide).</p>
      ) : (
        <p role="status" className={`mb-4 rounded-xl border p-3 text-sm ${data.compliant ? "border-border bg-surface" : "border-[var(--bad)] bg-[var(--bad-bg)] text-[var(--bad)]"}`}>
          Deployment region <b>{data.region}</b>; data may go to: {data.allowedRegions.join(", ")}. {data.strict ? "Strict: the server refuses to start otherwise." : "Not strict: problems are only warned about."}{" "}
          {data.compliant ? "Every destination is allowed." : `${data.problems.length} problem${data.problems.length === 1 ? "" : "s"}.`}
        </p>)}
      {data.problems.length > 0 && <ul className="mb-4 list-disc pl-5 text-sm text-[var(--bad)]">{data.problems.map((p, i) => <li key={i}>{p}</li>)}</ul>}
      <div className="overflow-x-auto rounded-xl border border-border bg-surface">
        <table className="w-full text-left text-sm">
          <thead className="text-muted"><tr><th className="p-2">Destination</th><th className="p-2">What it receives</th><th className="p-2">Host</th><th className="p-2">Region</th><th className="p-2">Status</th></tr></thead>
          <tbody>{data.flows.map((f, i) => (
            <tr key={i} className="border-t border-border align-top"><td className="p-2 font-medium">{f.name}</td><td className="p-2">{f.data}</td><td className="p-2"><code>{f.host ?? "unknown"}</code></td><td className="p-2">{f.region ?? "–"}</td><td className={`p-2 ${LABEL[f.status].cls}`}>{LABEL[f.status].text}</td></tr>))}
            {data.flows.length === 0 && <tr><td colSpan={5} className="p-3 text-muted">No outside destinations are configured.</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-muted">{data.note}</p>
    </>
  );
}
