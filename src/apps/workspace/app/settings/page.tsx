"use client";
import Link from "next/link";
import { useState } from "react";
import { getApiKey, resetMe, setApiKey, useMe } from "@northcx/api-client";
import { GlassCard, PageHeader, Segmented, Toggle, usePrefs, type Prefs } from "@northcx/ui";

export default function Settings() {
  const { me } = useMe();
  const [key, setKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [p, set] = usePrefs();
  return (
    <>
      <PageHeader title="Settings" subtitle="Sign-in and how the Workspace looks for you." />
      <div className="grid gap-4 lg:grid-cols-2">
        <GlassCard title="Sign in">
          <p className="text-sm text-muted">{me?.openMode ? "This server has no authentication configured." : me ? `Signed in as ${me.name} (${me.role.replace("_", " ")}).` : "Not signed in."}</p>
          <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); setApiKey(key.trim()); resetMe(); setSaved(true); setTimeout(() => location.reload(), 300); }}>
            <label htmlFor="k" className="sr-only">API key</label>
            <input id="k" type="password" className="field" placeholder={getApiKey() ? "A key is saved for this tab" : "Paste an API key"} value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" />
            <button className="btn btn-primary" disabled={!key.trim()}>Use key</button>
          </form>
          {saved && <p className="mt-2 text-xs text-muted" role="status">Saved for this browser tab.</p>}
          <p className="mt-3 text-xs text-muted">The key is kept for this tab only and sent to the NorthCX server. Admin and Workspace on different addresses sign in separately.</p>
        </GlassCard>
        <GlassCard title="Appearance (shared with Admin on the same address)">
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">Theme<Segmented<Prefs["theme"]> label="Theme" value={p.theme} onChange={(v) => set({ theme: v })} options={[{ value: "system", label: "Match device" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} /></div>
            <div className="flex flex-wrap items-center justify-between gap-2">Density<Segmented<Prefs["density"]> label="Density" value={p.density} onChange={(v) => set({ density: v })} options={[{ value: "compact", label: "Compact" }, { value: "comfortable", label: "Comfortable" }, { value: "spacious", label: "Spacious" }]} /></div>
            <div className="flex items-center justify-between gap-2">High contrast<Toggle label="High contrast" checked={p.contrast === "high"} onChange={(v) => set({ contrast: v ? "high" : "normal" })} /></div>
            <div className="flex items-center justify-between gap-2">Reduce motion<Toggle label="Reduce motion" checked={p.motion === "reduce"} onChange={(v) => set({ motion: v ? "reduce" : "system" })} /></div>
          </div>
          <p className="mt-3 text-xs text-muted">More options are in <Link className="underline" href={process.env.NEXT_PUBLIC_ADMIN_URL ? `${process.env.NEXT_PUBLIC_ADMIN_URL}/preferences` : "http://localhost:3001/preferences"}>Admin, Preferences</Link>.</p>
        </GlassCard>
      </div>
    </>
  );
}
