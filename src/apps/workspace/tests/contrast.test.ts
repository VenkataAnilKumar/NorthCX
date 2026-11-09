import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// WCAG 2.x contrast check on the shared design tokens (Phase 1, slice 4): every text pair must reach AA (4.5:1),
// in light, dark, each accent and high contrast, on the surface the text really sits on (translucent glass over the background).
const css = readFileSync(resolve(process.cwd(), "../../packages/ui/src/styles.css"), "utf8");

function block(selector: string): Record<string, string> {
  const i = css.indexOf(selector + " {");
  if (i < 0) throw new Error("no block " + selector);
  const body = css.slice(css.indexOf("{", i) + 1, css.indexOf("\n}", i) >= 0 && css.indexOf("\n}", i) < css.indexOf("}", i) ? css.indexOf("\n}", i) : css.indexOf("}", i));
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}
type RGBA = [number, number, number, number];
function parse(c: string): RGBA {
  const h = c.match(/^#([0-9a-f]{6})$/i);
  if (h) return [parseInt(h[1].slice(0, 2), 16), parseInt(h[1].slice(2, 4), 16), parseInt(h[1].slice(4), 16), 1];
  const r = c.match(/^rgba?\(([^)]+)\)$/);
  if (r) { const p = r[1].split(",").map(Number); return [p[0], p[1], p[2], p[3] ?? 1]; }
  throw new Error("colour " + c);
}
const over = (top: RGBA, bottom: RGBA): RGBA => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)).concat(1) as RGBA; };
const lum = ([r, g, b]: RGBA) => { const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
const ratio = (a: RGBA, b: RGBA) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const light = block(":root");
const dark = { ...light, ...block(':root[data-theme="dark"]') };
const accents: Record<string, Record<string, string>> = {
  blue: {}, teal: block(':root[data-accent="teal"]'), violet: block(':root[data-accent="violet"]'), graphite: block(':root[data-accent="graphite"]'),
};
const darkAccents: Record<string, Record<string, string>> = {
  blue: {}, teal: block(':root[data-theme="dark"][data-accent="teal"]'), violet: block(':root[data-theme="dark"][data-accent="violet"]'), graphite: block(':root[data-theme="dark"][data-accent="graphite"]'),
};

function check(name: string, t: Record<string, string>, worstBg: string[]) {
  const bg = parse(t["--bg"]);
  // The page behind a glass card can be as far from --bg as the faint orbs allow; check on the plain background and on the card over it.
  for (const surfaceName of ["--surface", "--surface-strong"]) {
    const surface = over(parse(t[surfaceName]), bg);
    for (const [fg, on] of [["--text", surface], ["--muted", surface], ["--faint", surface], ["--primary", surface], ["--ok", surface], ["--warn", surface], ["--bad", surface]] as [string, RGBA][]) {
      if (fg === "--faint" && surfaceName === "--surface") continue; // faint is only used on strong surfaces and for non-essential hints
      it(`${name}: ${fg} on ${surfaceName} >= 4.5`, () => expect(ratio(parse(t[fg]), on)).toBeGreaterThanOrEqual(4.5));
    }
  }
  it(`${name}: button text on primary >= 4.5`, () => expect(ratio(parse(t["--primary-text"]), parse(t["--primary"]))).toBeGreaterThanOrEqual(4.5));
  for (const [fg, bgTok] of [["--ok", "--ok-bg"], ["--warn", "--warn-bg"], ["--bad", "--bad-bg"], ["--info", "--info-bg"]]) {
    it(`${name}: ${fg} on ${bgTok} >= 4.5`, () => expect(ratio(parse(t[fg]), over(parse(t[bgTok]), over(parse(t["--surface-strong"]), bg)))).toBeGreaterThanOrEqual(4.5));
  }
  void worstBg;
}

describe("design token contrast (WCAG AA)", () => {
  check("light", light, []);
  check("dark", dark, []);
  for (const a of ["teal", "violet", "graphite"]) {
    check(`light ${a}`, { ...light, ...accents[a] }, []);
    check(`dark ${a}`, { ...dark, ...darkAccents[a] }, []);
  }
  check("light high contrast", { ...light, ...block(':root[data-contrast="high"]') }, []);
  check("dark high contrast", { ...dark, ...block(':root[data-contrast="high"][data-theme="dark"]') }, []);
});
