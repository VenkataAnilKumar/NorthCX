"use client";
import { getChannels, useLoad } from "@northcx/api-client";
import { ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

export default function Channels() {
  const { data, error, loading, reload } = useLoad(getChannels, []);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  return (
    <>
      <PageHeader title="Channels" subtitle="Where agents can talk to customers, and which of those this server has switched on. Credentials are set in the server's environment and are never shown." />
      <GlassCard title="Channels">
        <table className="tbl"><caption className="sr-only">Customer channels</caption>
          <thead><tr><th>Channel</th><th>State</th><th>Receives messages at</th></tr></thead>
          <tbody>{data.map((c) => (
            <tr key={c.id}>
              <td>{c.label}</td>
              <td className={c.configured ? "text-[var(--good)]" : "text-muted"}>{c.configured ? "On" : "Not set up"}</td>
              <td><code>{c.inbound}</code>{c.note && <div className="text-xs text-muted">{c.note}</div>}</td>
            </tr>))}</tbody></table>
        <p className="mt-3 text-xs text-muted">To switch a channel on, set its variables (see the Deployment Guide) and restart. Conversation counts per channel are on <a className="underline" href="/insights">Analytics</a>.</p>
      </GlassCard>
    </>
  );
}
