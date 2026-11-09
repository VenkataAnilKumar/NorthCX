"use client";
import type { ComponentType, ReactNode } from "react";
import { ThemeToggle } from "./theme";

export interface NavItem { href: string; label: string; icon?: string; badge?: number; soon?: boolean }
export interface NavGroup { label?: string; items: NavItem[] }
export interface Switcher { label: string; href: string; current?: boolean }
// The app passes its router link so this package does not depend on Next.js.
type LinkLike = ComponentType<{ href: string; className?: string; children?: ReactNode; "aria-current"?: "page" | undefined }>;

function isActive(path: string, href: string) {
  return href === "/" ? path === "/" : path === href || path.startsWith(href + "/");
}

export function AppShell(props: {
  appName: string; nav: NavGroup[]; path: string; Link: LinkLike; switcher?: Switcher[]; user?: ReactNode; top?: ReactNode; children: ReactNode;
}) {
  const { appName, nav, path, Link, switcher = [], user, top, children } = props;
  return (
    <div className="mx-auto flex min-h-screen max-w-[1500px] flex-col gap-4 p-3 md:flex-row md:p-5">
      <aside className="glass md:sticky md:top-5 md:h-[calc(100vh-2.5rem)] md:w-64 md:shrink-0 md:overflow-y-auto" aria-label="Sidebar">
        <div className="flex items-baseline gap-2 px-4 pt-4 pb-2">
          <span className="text-lg font-bold text-primary">NorthCX</span>
          <span className="text-xs text-muted">{appName}</span>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:overflow-visible">
          {nav.map((g, gi) => (
            <div key={gi} className="flex gap-1 md:flex-col">
              {g.label && <p className="hidden px-3 pt-3 pb-1 text-[0.7rem] font-semibold tracking-wide text-muted uppercase md:block">{g.label}</p>}
              {g.items.map((i) => {
                const active = isActive(path, i.href);
                return (
                  <Link key={i.href} href={i.href} aria-current={active ? "page" : undefined}
                    className={`flex items-center justify-between gap-2 rounded-xl px-3 py-2 text-sm whitespace-nowrap ${active ? "bg-primary font-semibold text-primary-text" : "text-muted hover:bg-[var(--info-bg)] hover:text-text"}`}>
                    <span>{i.icon ? <span aria-hidden="true" className="mr-2">{i.icon}</span> : null}{i.label}</span>
                    {i.badge ? <span className="rounded-full bg-[var(--bad-bg)] px-2 text-xs text-[var(--bad)]" aria-label={`${i.badge} waiting`}>{i.badge}</span> : null}
                    {i.soon ? <span className="rounded-full border border-border px-2 text-[0.65rem] text-muted">soon</span> : null}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        {user && <div className="border-t border-border px-4 py-3 text-xs text-muted">{user}</div>}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <header className="glass flex flex-wrap items-center gap-3 px-4 py-2.5">
          <div className="min-w-0 flex-1">{top}</div>
          {switcher.length > 0 && (
            <div className="flex items-center gap-1" role="group" aria-label="Switch app">
              {switcher.map((s) => (
                <a key={s.href} href={s.href} aria-current={s.current ? "page" : undefined} className={`pill ${s.current ? "font-semibold text-primary" : ""}`}>{s.label}</a>
              ))}
            </div>
          )}
          <ThemeToggle />
        </header>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
