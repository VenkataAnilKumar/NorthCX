"use client";
import { type Catalog, getCatalog, getLive, listAgents, previewSpec, releaseToEnvironment, saveSpec, type SpecPreview, useLoad, useMe } from "@northcx/api-client";
import { ToolPicker } from "@/components/tool-picker";
import { JourneyEditor } from "@/components/journey-editor";
import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { ErrorBox, Loading, PageHeader } from "@northcx/ui";

type Spec = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
type Ref = { name: string; config?: Record<string, unknown> };
const lines = (v: string) => v.split("\n").map((x) => x.trim()).filter(Boolean);
const box = "rounded-xl border border-border bg-surface p-4";
const input = "w-full rounded-lg border border-border bg-bg px-2 py-1.5 text-sm";

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return <section aria-label={title} className={box}><h2 className="font-medium">{title}</h2>{hint && <p className="mb-2 text-sm text-muted">{hint}</p>}<div className="mt-2 space-y-2">{children}</div></section>;
}

function RefPicker({ label, options, value, onChange, hints }: { label: string; options: { name: string; description?: string; example?: Record<string, unknown> | null }[]; value: Ref[]; onChange: (v: Ref[]) => void; hints?: boolean }) {
  const refs = (v: Ref[]) => v.map((r) => ({ name: r.name, config: r.config ?? {} }));
  return (
    <Section title={label}>
      {options.length === 0 && <p className="text-sm text-muted">None available.</p>}
      {options.map((o) => {
        const cur = value.find((r) => r.name === o.name);
        return (
          <div key={o.name}>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={!!cur} onChange={(e) => onChange(e.target.checked ? [...refs(value), { name: o.name, config: o.example ?? {} }] : refs(value).filter((r) => r.name !== o.name))} className="mt-1" />
              <span><code>{o.name}</code>{o.description && <span className="block text-muted">{o.description}</span>}</span>
            </label>
            {cur && hints && o.example && (
              <ConfigBox name={o.name} value={cur.config ?? {}} onChange={(c) => onChange(refs(value).map((r) => (r.name === o.name ? { ...r, config: c } : r)))} />)}
          </div>);
      })}
    </Section>
  );
}

function ConfigBox({ name, value, onChange }: { name: string; value: Record<string, unknown>; onChange: (c: Record<string, unknown>) => void }) {
  const [text, setText] = useState(JSON.stringify(value));
  const [bad, setBad] = useState(false);
  return (
    <div className="ml-6 mt-1">
      <label htmlFor={`cfg-${name}`} className="text-xs text-muted">Settings for {name} (JSON)</label>
      <input id={`cfg-${name}`} value={text} onChange={(e) => { setText(e.target.value); try { onChange(JSON.parse(e.target.value)); setBad(false); } catch { setBad(true); } }} className={`${input} font-mono text-xs`} aria-invalid={bad} />
      {bad && <p className="text-xs text-[var(--bad)]">Not valid JSON yet; the last valid settings are kept.</p>}
    </div>
  );
}

function Editor({ id, initial, catalog }: { id: string; initial: Spec; catalog: Catalog }) {
  const { can, askForName } = useMe();
  const [spec, setSpec] = useState<Spec>(initial);
  const [others, setOthers] = useState<string[]>([]);
  useEffect(() => { listAgents().then((a) => setOthers(a.map((x) => x.id).filter((x) => x !== id))).catch(() => setOthers([])); }, [id]);
  const routes: { agent: string; when: string }[] = spec.routes ?? [];
  const [preview, setPreview] = useState<SpecPreview | null>(null);
  const [note, setNote] = useState("");
  const [by, setBy] = useState("dev");
  const [saved, setSaved] = useState<{ number: number } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const always: string[] = spec.approvals?.always ?? [];
  const pick = (c: { tools: string[]; always: string[] }) => { set("tools", c.tools); set("approvals", c.always.length ? { always: c.always } : ""); };
  const set = (k: string, v: unknown) => { setSaved(null); setSpec((s) => { const n = { ...s }; if (v === "" || v === null || (Array.isArray(v) && v.length === 0)) delete n[k]; else n[k] = v; return n; }); };

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => { previewSpec(id, spec).then(setPreview).catch((e) => setPreview({ valid: false, problems: [(e as Error).message] })); }, 400);
    return () => clearTimeout(timer.current);
  }, [id, spec]);

  async function save() {
    setMsg(null);
    try { const v = await saveSpec(id, spec, askForName ? by.trim() || "dev" : undefined, note.trim() || undefined); setSaved({ number: v.number }); setNote(""); }
    catch (e) { setMsg((e as Error).message); }
  }
  async function tryInDev() {
    if (!saved) return;
    try { await releaseToEnvironment(id, saved.number, "dev", askForName ? by.trim() || "dev" : undefined); window.location.href = `/chat?agent=${encodeURIComponent(id)}&env=dev`; }
    catch (e) { setMsg((e as Error).message); }
  }

  const tools: string[] = spec.tools ?? [];
  const skills: { name: string; flexibility?: string }[] = spec.skills ?? [];
  const topics: { name: string; patterns: string[]; reply?: string }[] = spec.forced_handoff ?? [];
  const voice = spec.voice ?? {};
  const styles: Record<string, string> = spec.channel_styles ?? {};
  const accepted: string[] = spec.attachments ?? [];
  const languages: string[] = spec.languages ?? [];
  const LANGS: Record<string, string> = { en: "English", es: "Spanish", fr: "French", de: "German", pt: "Portuguese", it: "Italian", nl: "Dutch", ru: "Russian", ja: "Japanese", zh: "Chinese", ko: "Korean", ar: "Arabic", hi: "Hindi" };
  const setLanguages = (l: string[]) => set("languages", l.length ? l : null);
  const setVoice = (k: string, v: unknown) => set("voice", (() => { const n = { ...voice, [k]: v }; if (v === "" || (Array.isArray(v) && !v.length)) delete n[k]; return Object.keys(n).length ? n : null; })());
  const editable = can("versions:create");

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <fieldset disabled={!editable} className="space-y-4 border-0 p-0">
        <Section title="Instructions" hint="What the agent is for, how it should behave and what it must never do. Plain language.">
          <label htmlFor="instructions" className="sr-only">Instructions</label>
          <textarea id="instructions" value={spec.instructions ?? ""} onChange={(e) => set("instructions", e.target.value)} rows={12} className={`${input} font-mono`} />
          <p className="text-xs text-muted">{(spec.instructions ?? "").length} characters</p>
        </Section>
        <Section title="Model and limits">
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm">Model<input value={spec.model ?? ""} onChange={(e) => set("model", e.target.value)} placeholder="default" className={input} /></label>
            <label className="text-sm">Most steps per message<input type="number" min={1} max={50} value={spec.max_steps ?? 8} onChange={(e) => set("max_steps", Number(e.target.value))} className={input} /></label>
            <label className="text-sm">Token limit per message<input type="number" min={1000} value={spec.max_run_tokens ?? ""} onChange={(e) => set("max_run_tokens", e.target.value ? Number(e.target.value) : "")} placeholder="none" className={input} /></label>
          </div>
        </Section>
        <Section title="Tools" hint="What the agent can do. Tools that change things are marked; ones that need approval wait for a person.">
          <ToolPicker catalog={catalog} tools={tools} always={always} audience={spec.audience === "staff" ? "staff" : "customer"} onChange={pick} />
        </Section>
        <RefPicker label="Reply and tool checks" options={catalog.guardrails} value={spec.guardrails ?? []} onChange={(v) => set("guardrails", v)} hints />
        <RefPicker label="Customer message checks" options={catalog.inputGuardrails} value={spec.input_guardrails ?? []} onChange={(v) => set("input_guardrails", v)} />
        <RefPicker label="Tool result checks" options={catalog.outputGuardrails} value={spec.output_guardrails ?? []} onChange={(v) => set("output_guardrails", v)} />
        <Section title="Always send to a person" hint="Topics the agent must never handle alone. A message matching any pattern goes straight to a person.">
          {topics.map((t, i) => (
            <div key={i} className="rounded-lg border border-border p-3 text-sm">
              <div className="flex gap-2"><label className="flex-1">Topic name<input value={t.name} onChange={(e) => set("forced_handoff", topics.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} className={input} /></label>
                <button type="button" onClick={() => set("forced_handoff", topics.filter((_, j) => j !== i))} className="self-end rounded-lg border border-border px-2 py-1.5 hover:bg-border/40">Remove</button></div>
              <label className="mt-2 block">Patterns (one regular expression per line)<textarea value={t.patterns.join("\n")} onChange={(e) => set("forced_handoff", topics.map((x, j) => (j === i ? { ...x, patterns: lines(e.target.value) } : x)))} rows={2} className={`${input} font-mono text-xs`} /></label>
              <label className="mt-2 block">What the customer is told (optional)<input value={t.reply ?? ""} onChange={(e) => set("forced_handoff", topics.map((x, j) => (j === i ? { ...x, reply: e.target.value || undefined } : x)))} className={input} /></label>
            </div>))}
          <button type="button" onClick={() => set("forced_handoff", [...topics, { name: "", patterns: [] }])} className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-border/40">Add a topic</button>
        </Section>
        <Section title="Brand voice" hint="How the agent should sound. Words to avoid are enforced: a reply using one is rewritten.">
          <label className="block text-sm">Tone<input value={voice.tone ?? ""} onChange={(e) => setVoice("tone", e.target.value)} placeholder="warm and brief" className={input} /></label>
          <label className="block text-sm">Guidelines (one per line)<textarea value={(voice.guidelines ?? []).join("\n")} onChange={(e) => setVoice("guidelines", lines(e.target.value))} rows={2} className={input} /></label>
          <label className="block text-sm">Words and phrases to avoid (one per line)<textarea value={(voice.avoid_phrases ?? []).join("\n")} onChange={(e) => setVoice("avoid_phrases", lines(e.target.value))} rows={2} className={input} /></label>
          <label className="block text-sm">Sign-off<input value={voice.sign_off ?? ""} onChange={(e) => setVoice("sign_off", e.target.value)} className={input} /></label>
        </Section>
        <Section title="Skills" hint="Reusable know-how. Strict skills are enforced: steps must happen in order.">
          {catalog.skills.length === 0 && <p className="text-sm text-muted">No skills are installed.</p>}
          {catalog.skills.map((s) => {
            const cur = skills.find((x) => x.name === s.name);
            return (
              <div key={s.name} className="text-sm">
                <label className="flex items-start gap-2"><input type="checkbox" checked={!!cur} onChange={(e) => set("skills", e.target.checked ? [...skills, { name: s.name, flexibility: "guided" }] : skills.filter((x) => x.name !== s.name))} className="mt-1" />
                  <span><code>{s.name}</code><span className="block text-muted">{s.description}{s.steps.length ? ` Steps: ${s.steps.join(" → ")}` : ""}</span></span></label>
                {cur && <label className="ml-6 mt-1 block">How strictly<select value={cur.flexibility ?? "guided"} onChange={(e) => set("skills", skills.map((x) => (x.name === s.name ? { ...x, flexibility: e.target.value } : x)))} className="ml-2 rounded border border-border bg-bg px-1 py-0.5">
                  {catalog.flexibility.map((f) => <option key={f}>{f}</option>)}</select></label>}
              </div>);
          })}
        </Section>
        <Section title="Specialist agents" hint="Other agents this one may pass a conversation to, and when. The conversation then continues with the specialist, in the same turn and for later messages.">
          {routes.map((r, i) => (
            <div key={r.agent} className="flex gap-2 text-sm"><code className="self-center">{r.agent}</code>
              <input aria-label={`When to pass to ${r.agent}`} value={r.when} onChange={(e) => set("routes", routes.map((x, k) => (k === i ? { ...x, when: e.target.value } : x)))} className={input} />
              <button type="button" onClick={() => set("routes", routes.filter((_, k) => k !== i))} className="rounded-lg border border-border px-2 hover:bg-border/40">Remove</button></div>))}
          <form className="flex gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); const v = String(new FormData(e.currentTarget).get("specialist") ?? ""); if (v && !routes.some((r) => r.agent === v)) set("routes", [...routes, { agent: v, when: "Describe when to pass the conversation on" }]); }}>
            <label className="sr-only" htmlFor="newroute">Specialist agent</label>
            <select id="newroute" name="specialist" className={`${input} w-48`}><option value="">Choose an agent…</option>{others.filter((o) => !routes.some((r) => r.agent === o)).map((o) => <option key={o}>{o}</option>)}</select>
            <button className="rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">Add</button></form>
        </Section>
        <Section title="Journeys" hint="How a kind of conversation should go: a goal, steps tied to tools, rules, and when to hand over. Describe one in plain words and the model drafts it for you to review.">
          <JourneyEditor agent={id} journeys={spec.journeys ?? []} tools={Array.from(new Set([...tools, ...catalog.tools.map((t) => t.name)]))} onChange={(j) => set("journeys", j)} />
        </Section>
        <Section title="Attachments" hint="What customers may attach. Nothing is accepted unless ticked. Text files are checked like a typed message; pictures and PDFs reach the model as they are (personal data in them is not masked).">
          <div className="flex flex-wrap gap-4 text-sm">
            {([["image", "Pictures (PNG, JPEG, GIF, WebP)"], ["pdf", "PDF files"], ["text", "Plain text files"]] as const).map(([k, label]) => (
              <label key={k}><input type="checkbox" checked={accepted.includes(k)} onChange={(e) => set("attachments", e.target.checked ? [...accepted, k] : accepted.filter((x) => x !== k))} /> {label}</label>))}
          </div>
        </Section>
        <Section title="Languages" hint="Languages this agent is written and tested for. It detects what the customer writes in and replies in the same language; anything else gets the default and an offer of a person. Leave empty for no language handling.">
          <div className="flex flex-wrap gap-3 text-sm">
            {Object.entries(LANGS).map(([code, name]) => (
              <label key={code}><input type="checkbox" checked={languages.includes(code)} onChange={(e) => setLanguages(e.target.checked ? [...languages, code] : languages.filter((x) => x !== code))} /> {name}</label>))}
          </div>
          {languages.length > 1 && (
            <label className="text-sm">Default language<select value={languages[0]} onChange={(e) => setLanguages([e.target.value, ...languages.filter((x) => x !== e.target.value)])} className="ml-2 rounded border border-border bg-bg px-1 py-0.5">
              {languages.map((c) => <option key={c} value={c}>{LANGS[c] ?? c}</option>)}</select></label>)}
        </Section>
        <Section title="Style per channel" hint="Optional wording for a channel, for example sms: two short sentences, no formatting.">
          {Object.entries(styles).map(([ch, text]) => (
            <div key={ch} className="flex gap-2 text-sm"><code className="self-center">{ch}</code>
              <input aria-label={`Style for ${ch}`} value={text} onChange={(e) => set("channel_styles", { ...styles, [ch]: e.target.value })} className={input} />
              <button type="button" onClick={() => { const n = { ...styles }; delete n[ch]; set("channel_styles", Object.keys(n).length ? n : null); }} className="rounded-lg border border-border px-2 hover:bg-border/40">Remove</button></div>))}
          <form className="flex gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); const v = String(new FormData(e.currentTarget).get("channel") ?? "").trim().toLowerCase(); if (v && !(v in styles)) set("channel_styles", { ...styles, [v]: "Keep replies short" }); e.currentTarget.reset(); }}>
            <label className="sr-only" htmlFor="newch">Channel name</label><input id="newch" name="channel" placeholder="sms, email, web" className={`${input} w-40`} /><button className="rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">Add</button></form>
        </Section>
      </fieldset>

      <aside aria-label="Check and save" className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        <section className={box} aria-live="polite">
          <h2 className="font-medium">Checks</h2>
          {!preview ? <p className="text-sm text-muted">Checking…</p> : preview.valid ? (
            <div className="space-y-1 text-sm"><p className="text-[var(--ok)]">The agent is valid.</p>
              {preview.diffFromLive && !preview.diffFromLive.identical && <p className="text-muted">Differs from production:{preview.diffFromLive.instructions ? " instructions," : ""}{preview.diffFromLive.tools.added.length ? ` +${preview.diffFromLive.tools.added.join(", ")},` : ""}{preview.diffFromLive.tools.removed.length ? ` −${preview.diffFromLive.tools.removed.join(", ")},` : ""}{Object.keys(preview.diffFromLive.other).length ? ` settings: ${Object.keys(preview.diffFromLive.other).join(", ")}` : ""}</p>}
              {preview.diffFromLive?.identical && <p className="text-muted">Same as production.</p>}
              {preview.unchangedSinceLatest && <p className="text-muted">Already saved as the latest version.</p>}</div>
          ) : <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--bad)]">{preview.problems.map((p) => <li key={p}>{p}</li>)}</ul>}
        </section>
        <section className={box}>
          <h2 className="font-medium">Save</h2>
          {askForName && <label className="mt-2 block text-sm">Your name<input value={by} onChange={(e) => setBy(e.target.value)} className={input} /></label>}
          <label className="mt-2 block text-sm">What changed (optional)<input value={note} onChange={(e) => setNote(e.target.value)} className={input} /></label>
          <button onClick={save} disabled={!editable || !preview?.valid || preview.unchangedSinceLatest} className="mt-3 w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-text disabled:opacity-50">Save as new version</button>
          {!editable && <p className="mt-1 text-xs text-muted">Your role can look but not change.</p>}
          {msg && <p role="alert" className="mt-2 text-sm text-[var(--bad)]">{msg}</p>}
          {saved && (
            <div className="mt-3 space-y-2 text-sm" role="status">
              <p className="text-[var(--ok)]">Saved as version {saved.number}.</p>
              <button onClick={tryInDev} className="w-full rounded-lg border border-border px-3 py-1.5 hover:bg-border/40">Try it in dev</button>
              <Link className="block text-primary underline" href={`/agents/${id}`}>Run the checks and publish →</Link>
            </div>)}
        </section>
      </aside>
    </div>
  );
}

export default function Studio({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const live = useLoad(() => getLive(id), [id]);
  const catalog = useLoad(getCatalog, []);
  if ((live.loading && !live.data) || (catalog.loading && !catalog.data)) return <Loading />;
  if (live.error) return <ErrorBox message={live.error} onRetry={live.reload} />;
  if (catalog.error) return <ErrorBox message={catalog.error} onRetry={catalog.reload} />;
  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-primary underline" href={`/agents/${id}`}>← {id}: versions and releases</Link></p>
      <PageHeader title={`Edit ${id}`} subtitle="Change the agent without writing a file. Nothing goes live until you save a version, it passes its required scenarios, and you publish it." />
      <Editor key={`${id}-${live.data!.digest}`} id={id} initial={live.data!.spec as Spec} catalog={catalog.data!} />
    </>
  );
}
