"use client";
import { useState } from "react";
import { getApiKey, getMe, setApiKey } from "@/lib/api";
import { resetMe } from "@/lib/me";
import { PageHeader } from "@/components/states";

export default function Settings() {
  const [key, setKey] = useState(() => (typeof window === "undefined" ? "" : getApiKey()));
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setApiKey(key.trim());
    resetMe();
    try {
      const me = await getMe();
      setMsg({ ok: true, text: me.openMode ? "Connected. The server has no authentication configured (open mode)." : `Connected as ${me.name} (${me.role.replace("_", " ")}).` });
    } catch (err) {
      setMsg({ ok: false, text: `Could not connect: ${(err as Error).message}` });
    }
  }

  return (
    <>
      <PageHeader title="Settings" subtitle="Connection to the NorthCX backend." />
      <form onSubmit={save} className="max-w-md space-y-4 rounded-xl border border-border bg-surface p-4">
        <div>
          <label htmlFor="key" className="block text-sm font-medium">API key</label>
          <p className="mb-2 text-xs text-muted">Needed when the server requires keys. Create keys on the Access page. Kept in this browser tab only.</p>
          <input id="key" type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off"
            className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm" />
        </div>
        <button className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-text">Save and test</button>
        {msg && <p role="status" className={`text-sm ${msg.ok ? "text-[var(--ok)]" : "text-[var(--bad)]"}`}>{msg.text}</p>}
      </form>
    </>
  );
}
