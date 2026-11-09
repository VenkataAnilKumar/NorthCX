"use client";
import type { ReactNode } from "react";

export function GlassCard({ title, action, children, className = "" }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`glass p-4 ${className}`}>
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatTile({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: "ok" | "warn" | "bad" }) {
  const color = tone === "bad" ? "text-[var(--bad)]" : tone === "warn" ? "text-[var(--warn)]" : tone === "ok" ? "text-[var(--ok)]" : "";
  return (
    <div className="glass p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className={`mt-1 text-3xl font-bold ${color}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full border border-border-strong transition-colors ${checked ? "bg-primary" : "bg-[var(--border)]"}`}>
      <span className={`absolute top-0.5 h-4.5 w-4.5 rounded-full bg-white shadow transition-all ${checked ? "left-[1.4rem]" : "left-0.5"}`} />
    </button>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex gap-1 rounded-xl border border-border bg-[var(--surface)] p-1">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} onClick={() => onChange(o.value)}
          className={`rounded-lg px-3 py-1 text-sm ${o.value === value ? "bg-primary font-semibold text-primary-text" : "text-muted hover:text-text"}`}>{o.label}</button>
      ))}
    </div>
  );
}

/** For a tab whose backend is not built yet: say what it will do and what it waits for, instead of showing made-up data. */
export function ComingSoon({ title, what, needs }: { title: string; what: string; needs: string }) {
  return (
    <div className="glass mx-auto max-w-2xl p-8 text-center">
      <span className="pill mb-3">Not available yet</span>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-3 text-sm text-muted">{what}</p>
      <p className="mt-4 text-xs text-muted">Waiting for: {needs}</p>
    </div>
  );
}

export function Tabs({ items, active, Link }: { items: { href: string; label: string }[]; active: string; Link: React.ComponentType<{ href: string; className?: string; children?: ReactNode; "aria-current"?: "page" | undefined }> }) {
  return (
    <nav aria-label="Sections" className="mb-4 flex gap-1 overflow-x-auto border-b border-border">
      {items.map((t) => (
        <Link key={t.href} href={t.href} aria-current={t.href === active ? "page" : undefined}
          className={`px-3 py-2 text-sm whitespace-nowrap ${t.href === active ? "border-b-2 border-primary font-semibold text-primary" : "text-muted hover:text-text"}`}>{t.label}</Link>
      ))}
    </nav>
  );
}
