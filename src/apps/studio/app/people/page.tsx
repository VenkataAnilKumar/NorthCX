"use client";
import { useState } from "react";
import { addGroupMember, createGroup, deleteGroup, listGroups, removeGroupMember, updateGroup, useLoad, useMe, type GroupInfo } from "@northcx/api-client";
import { Empty, ErrorBox, GlassCard, Loading, PageHeader } from "@northcx/ui";

const ROLES = ["admin", "release_manager", "developer", "reviewer", "auditor", "viewer"];

function Group({ g, onChange }: { g: GroupInfo; onChange: () => void }) {
  const [member, setMember] = useState("");
  const [external, setExternal] = useState(g.externalName ?? "");
  const [error, setError] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>) => { setError(null); try { await fn(); onChange(); } catch (e) { setError((e as Error).message); } };
  const toggle = (role: string) => run(() => updateGroup(g.id, { roles: g.roles.includes(role) ? g.roles.filter((r) => r !== role) : [...g.roles, role] }));
  return (
    <GlassCard title={g.name} action={<button className="btn" onClick={() => void run(() => deleteGroup(g.id))}>Delete</button>}>
      {error && <div className="mb-2"><ErrorBox message={error} /></div>}
      <fieldset className="mb-3"><legend className="text-sm font-medium">Roles this group gives</legend>
        <div className="mt-1 flex flex-wrap gap-3 text-sm">{ROLES.map((r) => <label key={r} className="flex items-center gap-1"><input type="checkbox" checked={g.roles.includes(r)} onChange={() => void toggle(r)} />{r.replace("_", " ")}</label>)}</div>
        <p className="mt-1 text-xs text-muted">A person gets the combined permissions of every group they are in. Roles take effect at their next sign-in.</p></fieldset>
      <label className="text-sm" htmlFor={`ext-${g.id}`}>Identity provider group name</label>
      <div className="mt-1 flex gap-2"><input id={`ext-${g.id}`} className="field" value={external} onChange={(e) => setExternal(e.target.value)} placeholder="The name in your provider's groups claim" />
        <button className="btn" onClick={() => void run(() => updateGroup(g.id, { externalName: external }))}>Save</button></div>
      <h3 className="mb-1 mt-3 text-sm font-medium">Members added by hand ({g.members.length})</h3>
      {g.members.length ? <ul className="mb-2 space-y-1 text-sm">{g.members.map((m) => <li key={m} className="flex items-center justify-between gap-2"><span>{m}</span><button className="btn" aria-label={`Remove ${m}`} onClick={() => void run(() => removeGroupMember(g.id, m))}>Remove</button></li>)}</ul> : <p className="mb-2 text-xs text-muted">None. People in the provider group above are members automatically.</p>}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void run(() => addGroupMember(g.id, member)).then(() => setMember("")); }}>
        <label htmlFor={`m-${g.id}`} className="sr-only">Add a member by email</label>
        <input id={`m-${g.id}`} className="field" value={member} onChange={(e) => setMember(e.target.value)} placeholder="Add by email address" />
        <button className="btn" disabled={!member.trim()}>Add</button></form>
    </GlassCard>
  );
}

export default function People() {
  const { can } = useMe();
  const { data, error, loading, reload } = useLoad(() => listGroups());
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  if (!can("keys:manage")) return <Empty>Your role cannot manage groups. Ask an administrator.</Empty>;
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  return (
    <>
      <PageHeader title="People and groups" subtitle="Groups give roles to people, by email address or by the group name your identity provider sends. Single sign-on with groups is switched on by NORTHCX_SSO_USE_GROUPS; provisioning by NORTHCX_SCIM_TOKEN." />
      <form className="glass mb-4 flex gap-2 p-3" onSubmit={(e) => { e.preventDefault(); setErr(null); createGroup(name.trim(), []).then(() => { setName(""); reload(); }).catch((x) => setErr((x as Error).message)); }}>
        <label htmlFor="g-name" className="sr-only">New group name</label>
        <input id="g-name" className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="New group name, for example Support leads" />
        <button className="btn btn-primary" disabled={!name.trim()}>Create group</button>
      </form>
      {err && <div className="mb-3"><ErrorBox message={err} /></div>}
      {data!.length === 0 ? <Empty>No groups yet. Create one, give it roles, and add people or map it to a group from your identity provider.</Empty> : (
        <div className="grid gap-4 lg:grid-cols-2">{data!.map((g) => <Group key={g.id} g={g} onChange={reload} />)}</div>
      )}
    </>
  );
}
