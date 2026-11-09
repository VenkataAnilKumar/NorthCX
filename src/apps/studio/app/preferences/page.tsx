"use client";
import { GlassCard, PageHeader, Segmented, Toggle, usePrefs, type Prefs } from "@northcx/ui";

export default function Preferences() {
  const [p, set] = usePrefs();
  const row = (label: string, hint: string | undefined, control: React.ReactNode) => (
    <div className="flex flex-wrap items-center justify-between gap-3 py-2.5"><div><p className="text-sm font-medium">{label}</p>{hint && <p className="text-xs text-muted">{hint}</p>}</div>{control}</div>
  );
  return (
    <>
      <PageHeader title="Preferences" subtitle="How NorthCX looks for you. Saved in this browser and shared by the Admin and Workspace apps on the same address." />
      <div className="grid gap-4 lg:grid-cols-2">
        <GlassCard title="Theme">
          {row("Theme", "Match device follows your system setting.", <Segmented<Prefs["theme"]> label="Theme" value={p.theme} onChange={(v) => set({ theme: v })}
            options={[{ value: "system", label: "Match device" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} />)}
          {row("Accent colour", "Status colours (ok, warning, error) never change.", <Segmented<Prefs["accent"]> label="Accent colour" value={p.accent} onChange={(v) => set({ accent: v })}
            options={[{ value: "blue", label: "Blue" }, { value: "teal", label: "Teal" }, { value: "violet", label: "Violet" }, { value: "graphite", label: "Graphite" }]} />)}
        </GlassCard>
        <GlassCard title="Layout">
          {row("Density", undefined, <Segmented<Prefs["density"]> label="Density" value={p.density} onChange={(v) => set({ density: v })}
            options={[{ value: "compact", label: "Compact" }, { value: "comfortable", label: "Comfortable" }, { value: "spacious", label: "Spacious" }]} />)}
          {row("Text size", undefined, <Segmented<Prefs["text"]> label="Text size" value={p.text} onChange={(v) => set({ text: v })}
            options={[{ value: "small", label: "Small" }, { value: "medium", label: "Medium" }, { value: "large", label: "Large" }]} />)}
        </GlassCard>
        <GlassCard title="Accessibility">
          {row("High contrast", "Solid surfaces and stronger borders, no transparency.", <Toggle label="High contrast" checked={p.contrast === "high"} onChange={(v) => set({ contrast: v ? "high" : "normal" })} />)}
          {row("Solid surfaces", "Replaces the glass effect with plain surfaces.", <Toggle label="Solid surfaces" checked={p.glass === "solid"} onChange={(v) => set({ glass: v ? "solid" : "glass" })} />)}
          {row("Reduce motion", "Turns off transitions and animation.", <Toggle label="Reduce motion" checked={p.motion === "reduce"} onChange={(v) => set({ motion: v ? "reduce" : "system" })} />)}
          <p className="mt-2 text-xs text-muted">Transparency also turns off by itself when your system asks for reduced transparency.</p>
        </GlassCard>
        <GlassCard title="Preview">
          <div className="glass-strong rounded-xl p-4"><p className="font-semibold">Glass surface</p><p className="mt-1 text-sm text-muted">Text sits on a surface that stays readable over the background.</p>
            <div className="mt-3 flex gap-2"><button className="btn btn-primary">Primary</button><button className="btn">Secondary</button><span className="pill">Pill</span></div></div>
        </GlassCard>
      </div>
    </>
  );
}
