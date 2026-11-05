"use client";
import { useState } from "react";
import { type AuditEntry, createKey, formatTime, listAudit, listKeys, revokeKey, useLoad, useMe, verifyAudit } from "@northcx/api-client";
import { Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "@northcx/ui";

function Keys() {
  const { data, error, loading, reload } = useLoad(listKeys);
  const [name, setName] = useState("");
  const [role, setRole] = useState("viewer");
  const [days, setDays] = useState("");
  const [created, setCreated] = useState<{ name: string; key: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setCreated(null);
    try { const k = await createKey(name.trim(), role, days ? Number(days) : undefined); setCreated({ name: k.name, key: k.key }); setName(""); reload(); }
    catch (e2) { setErr((e2 as Error).message); }
  }
  async function revoke(id: string) {
    setErr(null);
    try { await revokeKey(id); reload(); } catch (e2) { setErr((e2 as Error).message); }
  }
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  return (
    <section aria-label="API keys" className="space-y-4">
      <h2 className="font-medium">API keys</h2>
      <form onSubmit={create} className="flex flex-wrap items-end gap-3 rounded-xl border border-border bg-surface p-4">
        <label className="text-sm">Name <input required value={name} onChange={(e) => setName(e.target.value)} className="ml-1 w-40 rounded-lg border border-border bg-bg px-2 py-1.5" /></label>
        <label className="text-sm">Role
          <select value={role} onChange={(e) => setRole(e.target.value)} className="ml-1 rounded-lg border border-border bg-bg px-2 py-1.5">
            {Object.keys(data!.roles).map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
          </select>
        </label>
        <label className="text-sm">Expires in (days) <input value={days} onChange={(e) => setDays(e.target.value)} inputMode="numeric" placeholder="never" className="ml-1 w-20 rounded-lg border border-border bg-bg px-2 py-1.5" /></label>
        <button className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-text">Create key</button>
        <p className="w-full text-xs text-muted">{role.replace("_", " ")} can: {data!.roles[role].join(", ")}</p>
      </form>
      {created && (
        <div role="status" className="rounded-xl border border-[var(--ok)] bg-[var(--ok-bg)] p-4 text-sm">
          <p className="font-medium text-[var(--ok)]">Key “{created.name}” created. Copy it now: it is shown only once.</p>
          <code className="mt-2 block break-all rounded-lg bg-bg p-2 text-xs">{created.key}</code>
          <button onClick={() => setCreated(null)} className="mt-2 text-xs underline">I have saved it</button>
        </div>
      )}
      {err && <ErrorBox message={err} />}
      <div className="overflow-x-auto rounded-xl border border-border bg-surface">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border text-muted"><tr>
            <th className="p-3 font-medium">Name</th><th className="p-3 font-medium">Role</th><th className="p-3 font-medium">Key</th>
            <th className="p-3 font-medium">Created</th><th className="p-3 font-medium">Last used</th><th className="p-3 font-medium">State</th><th className="p-3"><span className="sr-only">Actions</span></th>
          </tr></thead>
          <tbody>{data!.keys.map((k) => (
            <tr key={k.id} className="border-b border-border last:border-0">
              <td className="p-3">{k.name}</td><td className="p-3">{k.role.replace("_", " ")}</td><td className="p-3 font-mono text-xs">{k.prefix}…</td>
              <td className="p-3 whitespace-nowrap">{formatTime(k.createdAt)}<div className="text-xs text-muted">by {k.createdBy}</div></td>
              <td className="p-3 whitespace-nowrap">{k.lastUsedAt ? formatTime(k.lastUsedAt) : "never"}</td>
              <td className="p-3"><StatusBadge status={k.active ? "live" : "revoked"} /></td>
              <td className="p-3">{k.active && <button onClick={() => revoke(k.id)} className="text-[var(--bad)] underline">Revoke</button>}</td>
            </tr>))}
            {!data!.keys.length && <tr><td colSpan={7} className="p-4 text-center text-muted">No keys yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Audit() {
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const { data, error, loading, reload } = useLoad(() => listAudit(action || undefined, actor || undefined), [action, actor]);
  const [check, setCheck] = useState<string | null>(null);
  async function verify() {
    try {
      const v = await verifyAudit();
      setCheck(v.ok ? `The log is intact: ${v.checked} entries verified. Newest entry fingerprint: ${v.head?.slice(0, 16) ?? "none"}` : `The log has been tampered with at entry ${v.brokenAt}: ${v.reason}`);
    } catch (e) { setCheck((e as Error).message); }
  }
  return (
    <section aria-label="Audit log" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="font-medium">Audit log</h2>
        <div className="flex flex-wrap items-end gap-2 text-sm">
          <label>Action <input value={action} onChange={(e) => setAction(e.target.value)} placeholder="e.g. release.publish" className="ml-1 w-44 rounded-lg border border-border bg-surface px-2 py-1.5" /></label>
          <label>Who <input value={actor} onChange={(e) => setActor(e.target.value)} className="ml-1 w-32 rounded-lg border border-border bg-surface px-2 py-1.5" /></label>
          <button onClick={verify} className="rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">Verify integrity</button>
        </div>
      </div>
      {check && <p role="status" className={`rounded-lg border p-3 text-sm ${check.startsWith("The log is intact") ? "border-[var(--ok)] bg-[var(--ok-bg)] text-[var(--ok)]" : "border-[var(--bad)] bg-[var(--bad-bg)] text-[var(--bad)]"}`}>{check}</p>}
      {loading && !data ? <Loading /> : error ? <ErrorBox message={error} onRetry={reload} /> : !data?.length ? <Empty>No entries match.</Empty> : (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border text-muted"><tr>
              <th className="p-3 font-medium">When</th><th className="p-3 font-medium">Who</th><th className="p-3 font-medium">Action</th>
              <th className="p-3 font-medium">Target</th><th className="p-3 font-medium">Outcome</th><th className="p-3 font-medium">Detail</th>
            </tr></thead>
            <tbody>{data.map((e: AuditEntry) => (
              <tr key={e.id} className="border-b border-border align-top last:border-0">
                <td className="p-3 whitespace-nowrap">{formatTime(e.at)}</td>
                <td className="p-3">{e.actor}<div className="text-xs text-muted">{e.role}</div></td>
                <td className="p-3"><code>{e.action}</code></td>
                <td className="p-3 break-all">{e.target}</td>
                <td className="p-3"><StatusBadge status={e.outcome === "success" ? "passed" : e.outcome === "blocked" ? "blocked" : "failed"} /></td>
                <td className="p-3 max-w-xs break-words text-xs text-muted">{JSON.stringify(e.detail)}</td>
              </tr>))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function Access() {
  const { can, me } = useMe();
  return (
    <>
      <PageHeader title="Access and audit" subtitle="Who can sign in and what they can do, and a tamper-evident record of what has been done." />
      {me?.openMode && <p role="alert" className="mb-4 rounded-lg border border-[var(--warn)] bg-[var(--warn-bg)] p-3 text-sm text-[var(--warn)]">No authentication is configured on the server, so everyone has admin access. Set NORTHCX_API_KEY or create a key to turn authentication on.</p>}
      <div className="space-y-8">
        {can("keys:manage") && <Keys />}
        {can("audit:read") && <Audit />}
        {me && !can("keys:manage") && !can("audit:read") && <Empty>Your role cannot manage keys or read the audit log.</Empty>}
      </div>
    </>
  );
}
