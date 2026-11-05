"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getApiKey, getMe, resetMe, setApiKey } from "@northcx/api-client";
import { PageHeader } from "@northcx/ui";

/** Where single sign-on lands. The session arrives in the URL fragment (never sent to a server); it is stored for this tab and removed from the address bar. */
export default function SsoLanding() {
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    const hash = new URLSearchParams(window.location.hash.slice(1));
    const query = new URLSearchParams(window.location.search);
    const token = hash.get("token");
    window.history.replaceState(null, "", window.location.pathname);
    if (!token) { setState({ ok: false, text: query.get("error") ?? "No sign-in was received." }); return; }
    const previous = getApiKey();
    setApiKey(token);
    resetMe();
    getMe().then((me) => setState({ ok: true, text: `Signed in as ${me.name} (${me.role.replace("_", " ")}).` }))
      .catch((e: Error) => { setApiKey(previous); resetMe(); setState({ ok: false, text: `Sign-in did not work: ${e.message}` }); });
  }, []);
  return (
    <>
      <PageHeader title="Single sign-on" />
      {state === null ? <p role="status" className="text-sm text-muted">Finishing sign-in…</p> : (
        <div className="max-w-md space-y-3 rounded-xl border border-border bg-surface p-4">
          <p role={state.ok ? "status" : "alert"} className={`text-sm ${state.ok ? "text-[var(--ok)]" : "text-[var(--bad)]"}`}>{state.text}</p>
          {state.ok ? <Link href="/" className="text-sm text-primary underline">Go to the overview</Link> : <Link href="/settings" className="text-sm text-primary underline">Back to Settings</Link>}
        </div>
      )}
    </>
  );
}
