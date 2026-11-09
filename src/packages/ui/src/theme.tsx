"use client";
import { useCallback, useEffect, useState } from "react";

export interface Prefs {
  theme: "system" | "light" | "dark";
  accent: "blue" | "teal" | "violet" | "graphite";
  density: "compact" | "comfortable" | "spacious";
  text: "small" | "medium" | "large";
  contrast: "normal" | "high";
  motion: "system" | "reduce";
  /** "solid" turns every glass surface opaque (reduce transparency). */
  glass: "glass" | "solid";
  /** Left navigation: the full rail or icons only. Full window is a temporary mode and is not saved. */
  nav: "expanded" | "collapsed";
}
export const DEFAULT_PREFS: Prefs = { theme: "system", accent: "blue", density: "comfortable", text: "medium", contrast: "normal", motion: "system", glass: "glass", nav: "expanded" };
export const PREFS_KEY = "northcx.prefs";

/** Set the attributes the stylesheet reads. "system" and the defaults leave the attribute off. */
export function applyPrefs(p: Prefs, root: HTMLElement = document.documentElement): void {
  const set = (name: string, value: string | null) => (value ? root.setAttribute(name, value) : root.removeAttribute(name));
  set("data-theme", p.theme === "system" ? null : p.theme);
  set("data-accent", p.accent === "blue" ? null : p.accent);
  set("data-density", p.density === "comfortable" ? null : p.density);
  set("data-text", p.text === "medium" ? null : p.text);
  set("data-contrast", p.contrast === "normal" ? null : p.contrast);
  set("data-motion", p.motion === "system" ? null : p.motion);
  set("data-glass", p.glass === "glass" ? null : p.glass);
}

export function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    return raw ? { ...DEFAULT_PREFS, ...(JSON.parse(raw) as Partial<Prefs>) } : DEFAULT_PREFS;
  } catch {
    return DEFAULT_PREFS;
  }
}

/** Preferences are kept in this browser for now (a per-person server store comes later). Every app on the same address shares them. */
export function usePrefs(): [Prefs, (patch: Partial<Prefs>) => void] {
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT_PREFS);
  useEffect(() => setPrefs(loadPrefs()), []);
  const update = useCallback((patch: Partial<Prefs>) => {
    setPrefs((old) => {
      const next = { ...old, ...patch };
      applyPrefs(next);
      try { localStorage.setItem(PREFS_KEY, JSON.stringify(next)); } catch { /* private window: the choice lasts for this page only */ }
      return next;
    });
  }, []);
  return [prefs, update];
}

/** Runs before first paint so a saved dark theme does not flash light. Put it inside <head>. */
export function ThemeScript() {
  const code = `try{var p=JSON.parse(localStorage.getItem(${JSON.stringify(PREFS_KEY)})||"{}"),r=document.documentElement;
if(p.theme&&p.theme!=="system")r.setAttribute("data-theme",p.theme);
if(p.accent&&p.accent!=="blue")r.setAttribute("data-accent",p.accent);
if(p.density&&p.density!=="comfortable")r.setAttribute("data-density",p.density);
if(p.text&&p.text!=="medium")r.setAttribute("data-text",p.text);
if(p.contrast&&p.contrast!=="normal")r.setAttribute("data-contrast",p.contrast);
if(p.motion&&p.motion!=="system")r.setAttribute("data-motion",p.motion);
if(p.glass&&p.glass!=="glass")r.setAttribute("data-glass",p.glass);}catch(e){}`;
  return <script dangerouslySetInnerHTML={{ __html: code }} />;
}

export function ThemeToggle() {
  const [prefs, update] = usePrefs();
  const order: Prefs["theme"][] = ["system", "light", "dark"];
  const next = order[(order.indexOf(prefs.theme) + 1) % order.length];
  const label = { system: "Match device", light: "Light", dark: "Dark" }[prefs.theme];
  return (
    <button type="button" className="pill" onClick={() => update({ theme: next })} aria-label={`Theme: ${label}. Switch to ${next}.`} title={`Theme: ${label}`}>
      {prefs.theme === "dark" ? "☾" : prefs.theme === "light" ? "☀" : "◐"} {label}
    </button>
  );
}
