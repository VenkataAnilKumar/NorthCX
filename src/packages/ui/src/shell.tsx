"use client";
import { useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode } from "react";
import { NavIcon, type IconName } from "./icons";
import { ThemeToggle, usePrefs } from "./theme";

export interface SubItem { href: string; label: string; badge?: number; soon?: boolean }
/** One of the six left items. Pages sit inside it as sub-tabs; with one visible sub-tab no sub-tab row is shown. */
export interface NavItem { href: string; label: string; icon: IconName; badge?: number; children?: SubItem[] }
export interface Switcher { label: string; href: string; current?: boolean }
// The app passes its router link so this package does not depend on Next.js.
type LinkLike = ComponentType<{ href: string; className?: string; children?: ReactNode; title?: string; "aria-current"?: "page" | undefined; "aria-label"?: string }>;

export function isActive(path: string, href: string) {
  return href === "/" ? path === "/" : path === href || path.startsWith(href + "/");
}
/** Which left item owns this path: the one whose own href or a sub-tab href matches, preferring the longest match. */
export function activeItem(nav: NavItem[], path: string): { item: NavItem | undefined; sub: SubItem | undefined } {
  let best: { item: NavItem; sub?: SubItem; len: number } | undefined;
  for (const item of nav) {
    const hrefs: { href: string; sub?: SubItem }[] = [{ href: item.href }, ...(item.children ?? []).map((c) => ({ href: c.href, sub: c }))];
    for (const h of hrefs) {
      if (isActive(path, h.href) && (!best || h.href.length > best.len)) best = { item, sub: h.sub, len: h.href.length };
    }
  }
  return { item: best?.item, sub: best?.sub };
}
export function itemBadge(i: NavItem): number | undefined {
  const own = i.badge ?? 0; const kids = (i.children ?? []).reduce((n, c) => n + (c.badge ?? 0), 0);
  return own + kids || undefined;
}

const lastKey = (app: string) => `northcx.lastTab.${app}`;
function readLast(app: string): Record<string, string> {
  try { return JSON.parse(localStorage.getItem(lastKey(app)) || "{}"); } catch { return {}; }
}

export function SubTabs({ items, path, Link }: { items: SubItem[]; path: string; Link: LinkLike }) {
  let current = -1, len = -1;
  items.forEach((t, i) => { if (isActive(path, t.href) && t.href.length > len) { current = i; len = t.href.length; } });
  return (
    <nav aria-label="Sections" className="seg">
      {items.map((t, i) => (
        <Link key={t.href} href={t.href} aria-current={i === current ? "page" : undefined}>
          {t.label}{t.soon ? <span className="seg-soon">soon</span> : null}{t.badge ? <span className="seg-badge" aria-label={`${t.badge} waiting`}>{t.badge}</span> : null}
        </Link>
      ))}
    </nav>
  );
}

function useNarrow(px = 1100) {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const q = window.matchMedia(`(max-width: ${px - 1}px)`);
    const on = () => setNarrow(q.matches);
    on(); q.addEventListener("change", on);
    return () => q.removeEventListener("change", on);
  }, [px]);
  return narrow;
}

function Palette({ entries, Link, onClose }: { entries: { href: string; label: string; group: string }[]; Link: LinkLike; onClose: () => void }) {
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const list = useMemo(() => entries.filter((e) => `${e.group} ${e.label}`.toLowerCase().includes(q.trim().toLowerCase())).slice(0, 12), [entries, q]);
  useEffect(() => { ref.current?.querySelector("input")?.focus(); }, []);
  return (
    <div className="palette" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="glass glass-strong palette-box" role="dialog" aria-modal="true" aria-label="Jump to a page" ref={ref}
        onKeyDown={(e) => {
          if (e.key === "Escape") { e.preventDefault(); onClose(); }
          if (e.key === "Enter") { (ref.current?.querySelector("a") as HTMLAnchorElement | null)?.click(); onClose(); }
        }}>
        <input className="field text-base" placeholder="Jump to a page…" aria-label="Jump to a page" value={q} onChange={(e) => setQ(e.target.value)} />
        <ul className="mt-2 max-h-72 overflow-y-auto text-sm">
          {list.length === 0 ? <li className="px-3 py-2 text-muted">Nothing matches.</li> : list.map((e) => (
            <li key={e.href + e.label}><Link href={e.href} className="flex justify-between rounded-lg px-3 py-2 hover:bg-[var(--accent-soft)]"><span>{e.label}</span><span className="text-xs text-muted">{e.group}</span></Link></li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function AppShell(props: {
  appName: string; nav: NavItem[]; path: string; Link: LinkLike; switcher?: Switcher[]; user?: ReactNode; top?: ReactNode; children: ReactNode;
}) {
  const { appName, nav, path, Link, switcher = [], user, top, children } = props;
  const [prefs, update] = usePrefs();
  const narrow = useNarrow();
  const [full, setFull] = useState(false);
  const [palette, setPalette] = useState(false);
  const collapsed = prefs.nav === "collapsed" || narrow;
  const { item: current } = activeItem(nav, path);
  const subs = current?.children ?? [];
  const [last, setLast] = useState<Record<string, string>>({});
  useEffect(() => { setLast(readLast(appName)); }, [appName]);
  useEffect(() => {
    // Each group remembers the last sub-tab used.
    const { item, sub } = activeItem(nav, path);
    if (!item || !sub) return;
    setLast((l) => {
      if (l[item.href] === sub.href) return l;
      const next = { ...l, [item.href]: sub.href };
      try { localStorage.setItem(lastKey(appName), JSON.stringify(next)); } catch { /* storage can be blocked */ }
      return next;
    });
  }, [nav, path, appName]);
  const target = (i: NavItem) => {
    const remembered = i.children?.find((c) => c.href === last[i.href]);
    return remembered?.href ?? i.children?.[0]?.href ?? i.href;
  };
  const toggleNav = useCallback(() => update({ nav: prefs.nav === "collapsed" ? "expanded" : "collapsed" }), [prefs.nav, update]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((v) => !v); }
      else if (mod && e.key.toLowerCase() === "b") { e.preventDefault(); toggleNav(); }
      else if (mod && e.key === ".") { e.preventDefault(); setFull((v) => !v); }
      else if (e.key === "Escape" && full && !palette) setFull(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleNav, full, palette]);

  const entries = useMemo(() => nav.flatMap((i) => [{ href: i.href, label: i.label, group: appName }, ...(i.children ?? []).map((c) => ({ href: c.href, label: c.label, group: i.label }))]), [nav, appName]);

  return (
    <div className={`mx-auto flex min-h-screen max-w-[1560px] gap-4 p-3 md:p-4 ${full ? "pl-[4.5rem] pt-14" : ""}`}>
      {!full && (
        <aside className={`glass flex shrink-0 flex-col md:sticky md:top-4 md:h-[calc(100vh-2rem)] ${collapsed ? "rail-collapsed w-[4.5rem] px-2 py-3" : "w-[14.5rem] px-3 py-4"}`} aria-label="Sidebar">
          <div className={`pb-3 ${collapsed ? "text-center text-sm font-bold" : "px-2 text-base font-bold"}`}>
            {collapsed ? <span title={`NorthCX ${appName}`}>N</span> : <>NorthCX <span className="ml-1 text-xs font-medium text-muted">{appName}</span></>}
          </div>
          <nav aria-label="Main" className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overflow-x-hidden">
            {nav.map((i) => {
              const active = current?.href === i.href;
              const badge = itemBadge(i);
              return (
                <Link key={i.href} href={target(i)} className="rail-link" aria-current={active ? "page" : undefined} aria-label={collapsed ? `${i.label}${badge ? `, ${badge} waiting` : ""}` : undefined}>
                  <NavIcon name={i.icon} />
                  <span className="rail-label">{i.label}</span>
                  {badge ? <span className="rail-badge" aria-label={`${badge} waiting`}>{badge}</span> : null}
                  {collapsed ? <span className="rail-tip" role="presentation">{i.label}{badge ? ` · ${badge} waiting` : ""}</span> : null}
                </Link>
              );
            })}
          </nav>
          <div className="mt-2 flex flex-col gap-2">
            {!narrow && <button type="button" className="rail-link" onClick={toggleNav} aria-label={collapsed ? "Expand navigation" : "Collapse navigation"} title={`${collapsed ? "Expand" : "Collapse"} (Ctrl B)`}>
              <NavIcon name={collapsed ? "Expand" : "Collapse"} /><span className="rail-label">{collapsed ? "Expand" : "Collapse"}</span>
            </button>}
            {user && !collapsed && <div className="border-t border-border px-2 pt-3 text-xs text-muted">{user}</div>}
          </div>
        </aside>
      )}
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        {!full && (
          <header className="glass flex flex-wrap items-center gap-3 px-3 py-2">
            <button type="button" className="field flex min-w-[12rem] flex-1 cursor-text items-center gap-2 text-left text-muted" onClick={() => setPalette(true)} aria-label="Search or jump to a page (Ctrl K)">
              <NavIcon name="Search" className="rail-icon !h-4 !w-4" /><span className="flex-1 text-sm">{top ?? "Search or jump to…"}</span><span className="kbd">Ctrl K</span>
            </button>
            {switcher.length > 0 && (
              <div className="flex items-center gap-1" role="group" aria-label="Switch app">
                {switcher.map((s) => <a key={s.href} href={s.href} aria-current={s.current ? "page" : undefined} className={`pill ${s.current ? "font-semibold text-primary" : ""}`}>{s.label}</a>)}
              </div>
            )}
            <button type="button" className="pill" onClick={() => setFull(true)} title="Use the whole window (Ctrl .)" aria-label="Full window">Full window</button>
            <ThemeToggle />
          </header>
        )}
        {subs.filter((s) => s).length > 1 && <div><SubTabs items={subs} path={path} Link={Link} /></div>}
        <main className="min-w-0 flex-1">{children}</main>
      </div>
      {full && (
        <>
          <button type="button" className="glass fw-handle rounded-2xl p-3" onClick={() => setFull(false)} aria-label="Show navigation" title="Show navigation (Esc)"><NavIcon name="Menu" /></button>
          <div className="glass fw-pill flex items-center gap-2 rounded-full px-4 py-1.5 text-xs text-muted" role="status"><span>Full window</span><span className="kbd">Esc</span><span>to show navigation</span></div>
        </>
      )}
      {palette && <Palette entries={entries} Link={Link} onClose={() => setPalette(false)} />}
    </div>
  );
}
