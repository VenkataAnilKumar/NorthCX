"use client";
import { useState } from "react";
import { approveConnectionTools, checkConnection, createConnection, deleteConnection, listConnections, reviewConnection, updateConnection, useLoad, useMe,
  type Connection, type ConnectionCheck, type ConnectionReview } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** What a check found, in plain words: what to do is in the sentence. */
function describeCheck(c: ConnectionCheck): string[] {
  if (!c.reachable) return [`The server did not answer: ${c.message ?? "no reason given"}`];
  const lines: string[] = [];
  if (c.changed.length) lines.push(`Changed since you approved them, so they are switched off until you review and approve them again: ${c.changed.join(", ")}.`);
  if (c.added.length) lines.push(`New on the server and not usable until you approve them: ${c.added.join(", ")}.`);
  if (c.removed.length) lines.push(`The server no longer offers: ${c.removed.join(", ")}.`);
  return lines.length ? lines : ["Nothing has changed since you approved the tools."];
}

function AddForm({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [trusted, setTrusted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setError(null); setBusy(true);
    try { await createConnection({ name: name.trim(), url: url.trim(), secret: secret.trim() || null, trusted }); setName(""); setUrl(""); setSecret(""); setTrusted(false); onAdded(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <GlassCard title="Add a connection">
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <label className="text-sm">Name<input className="field mt-1" value={name} onChange={(e) => setName(e.target.value)} maxLength={24} required aria-describedby="name-help" />
          <span id="name-help" className="text-xs text-muted">Lowercase letters, digits and hyphens. It starts the name of every tool, for example shop__order_lookup.</span></label>
        <label className="text-sm">Address<input className="field mt-1" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://mcp.example.com/mcp" required aria-describedby="url-help" />
          <span id="url-help" className="text-xs text-muted">Must start with https:// and be on the allowed hosts above.</span></label>
        <label className="text-sm">Credential (optional)<input className="field mt-1" value={secret} onChange={(e) => setSecret(e.target.value)} aria-describedby="secret-help" />
          <span id="secret-help" className="text-xs text-muted">The name of the secret that holds the key or token, set by the person who runs NorthCX. Never the key itself.</span></label>
        <label className="flex items-start gap-2 text-sm sm:mt-6"><input type="checkbox" className="mt-1" checked={trusted} onChange={(e) => setTrusted(e.target.checked)} />
          <span>I trust this server to say which of its tools only read. Without this, every tool waits for a person before it runs.</span></label>
        <div className="sm:col-span-2"><button className="btn btn-primary" disabled={busy}>Add connection</button></div>
      </form>
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
    </GlassCard>
  );
}

function ReviewPanel({ c, onApproved }: { c: Connection; onApproved: () => void }) {
  const [review, setReview] = useState<ConnectionReview | null>(null);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const look = async () => {
    setError(null); setSaved(null);
    try { const r = await reviewConnection(c.id); setReview(r); setPicked(Object.fromEntries(r.tools.map((t) => [t.name, t.approved]))); } catch (e) { setError((e as Error).message); }
  };
  const approve = async () => {
    if (!review) return;
    setError(null); setSaved(null);
    try {
      const chosen = Object.fromEntries(review.tools.filter((t) => picked[t.name]).map((t) => [t.name, t.fingerprint]));
      const done = await approveConnectionTools(c.id, chosen);
      setSaved(`Saved. ${plural(done.approvedTools.length, "tool is", "tools are")} approved for agents to use.`);
      onApproved();
    } catch (e) { const message = (e as Error).message; await look(); setError(message); }  // look again at what the server offers now, and keep the reason on screen
  };
  return (
    <div className="mt-3 border-t pt-3">
      <button className="btn" onClick={() => void look()}>{review ? "Look again" : "Review the tools"}</button>
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
      {review && (
        <div className="mt-3">
          {review.tools.length === 0 ? <p className="text-sm text-muted">The server offers no tools that can be used.</p> : (
            <fieldset>
              <legend className="text-sm font-semibold">Tools agents may use</legend>
              <p className="text-xs text-muted">Nothing is approved until you press the button below. Agents see exactly the tool as it is described here.</p>
              <ul className="mt-2 space-y-2">
                {review.tools.map((t) => (
                  <li key={t.name}>
                    <label className="flex items-start gap-2 text-sm">
                      <input type="checkbox" className="mt-1" checked={!!picked[t.name]} onChange={(e) => setPicked({ ...picked, [t.name]: e.target.checked })} />
                      <span><strong>{t.name}</strong> <span className="pill ml-1">{t.access === "reads" ? "Only reads" : "Can change things: waits for a person"}</span>
                        {t.approved && <span className="pill ml-1">Approved</span>}
                        <span className="block text-muted">{t.description}</span>
                        {t.inputs.length > 0 && <span className="block text-xs text-muted">Needs: {t.inputs.join(", ")}</span>}</span>
                    </label>
                  </li>
                ))}
              </ul>
              <button className="btn btn-primary mt-3" onClick={() => void approve()}>Approve the ticked tools</button>
            </fieldset>
          )}
          {review.skipped.length > 0 && (
            <div className="mt-3 text-sm"><p className="font-semibold">Left out</p>
              <ul className="list-disc pl-5 text-muted">{review.skipped.map((s) => <li key={s.name}>{s.name}: {s.reason}</li>)}</ul></div>
          )}
          {saved && <p className="mt-2 text-sm" role="status">{saved}</p>}
        </div>
      )}
    </div>
  );
}

function ConnectionCard({ c, manage, onChanged }: { c: Connection; manage: boolean; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [checking, setChecking] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sure, setSure] = useState(false);
  const run = async (fn: () => Promise<unknown>) => { setError(null); try { await fn(); onChanged(); } catch (e) { setError((e as Error).message); } };
  return (
    <GlassCard title={c.name} action={<span><span className="pill">{c.enabled ? "On" : "Off"}</span> <span className="pill">{c.trusted ? "Trusted" : "Not trusted"}</span></span>}>
      <p className="text-sm">{c.host} · credential: {c.secret ?? "none"} · {plural(c.approvedTools.length, "tool approved", "tools approved")}</p>
      {c.approvedTools.length > 0 && <p className="text-xs text-muted">{c.approvedTools.join(", ")}</p>}
      {!c.enabled && <p className="text-xs text-muted">Switched off: agents cannot use any of its tools, including in conversations that are already running.</p>}
      {manage && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button className="btn" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Hide tools" : "Tools"}</button>
          <button className="btn" onClick={() => void run(async () => setChecking(describeCheck(await checkConnection(c.id))))}>Check for changes</button>
          <button className="btn" onClick={() => void run(() => updateConnection(c.id, { enabled: !c.enabled }))}>{c.enabled ? "Switch off" : "Switch on"}</button>
          <button className="btn" onClick={() => void run(() => updateConnection(c.id, { trusted: !c.trusted }))}>{c.trusted ? "Stop trusting" : "Trust this server"}</button>
          {sure ? <button className="btn" onClick={() => void run(() => deleteConnection(c.id))}>Yes, delete {c.name}</button> : <button className="btn" onClick={() => setSure(true)}>Delete</button>}
        </div>
      )}
      {checking && <ul className="mt-2 space-y-1 text-sm" role="status">{checking.map((l) => <li key={l}>{l}</li>)}</ul>}
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
      {manage && open && <ReviewPanel c={c} onApproved={onChanged} />}
    </GlassCard>
  );
}

export default function Connections() {
  const { can } = useMe();
  const { data, error, loading, reload } = useLoad(() => listConnections());
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const manage = can("keys:manage");
  const hosts = data!.allowedHosts;
  return (
    <>
      <PageHeader title="Connections" subtitle="Tools from other systems that agents can use, reached through the MCP standard. Only an administrator can add or change a connection." />
      <GlassCard title="Allowed hosts">
        {hosts.length ? <p className="text-sm">{hosts.join(", ")}</p> : <p className="text-sm text-muted">No hosts are allowed yet, so no connection can be added. Ask the person who runs NorthCX to set NORTHCX_MCP_HOSTS, then come back.</p>}
      </GlassCard>
      {manage && hosts.length > 0 && <div className="mt-4"><AddForm onAdded={reload} /></div>}
      <div className="mt-4 space-y-4">
        {data!.connections.length === 0 ? <Empty>No connections yet.</Empty> : data!.connections.map((c) => <ConnectionCard key={c.id} c={c} manage={manage} onChanged={reload} />)}
      </div>
    </>
  );
}
