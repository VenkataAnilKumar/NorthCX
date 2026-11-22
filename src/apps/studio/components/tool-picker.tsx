import type { Catalog } from "@northcx/api-client";
import { chooseTool, setAlways, unguarded } from "@/lib/approvals";
import { toolGroups } from "@/lib/tool-groups";

/** The tools an agent may use, from the catalogue, grouped by where they come from. A tool that changes things starts out needing a person's OK. */
export function ToolPicker({ catalog, tools, always, audience = "customer", onChange }: { catalog: Catalog; tools: string[]; always: string[]; audience?: "customer" | "staff"; onChange: (c: { tools: string[]; always: string[] }) => void }) {
  const usable = catalog.tools.filter((t) => t.audience === audience);  // a customer agent cannot use a staff tool, nor a staff agent a customer tool
  const loose = unguarded({ tools, always }, usable);
  return (
    <>
      {toolGroups(usable).map((g) => (
        <fieldset key={g.title} className="space-y-2"><legend className="text-xs font-medium text-muted">{g.title}</legend>
          {g.tools.map((t) => (
            <div key={t.name}>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" checked={tools.includes(t.name)} onChange={(e) => onChange(chooseTool({ tools, always }, t.name, e.target.checked, t.effect === "write"))} className="mt-1" />
                <span><code>{t.name}</code> <span className="rounded bg-border/60 px-1 text-xs">{t.effect === "write" ? "changes things" : "read only"}</span>{t.approval && <span className="ml-1 rounded bg-[var(--info-bg)] px-1 text-xs text-[var(--info)]">can need approval</span>}
                  <span className="block text-muted">{t.description}</span></span>
              </label>
              {tools.includes(t.name) && (
                <label className="ml-6 flex items-center gap-2 text-xs"><input type="checkbox" checked={always.includes(t.name)} onChange={(e) => onChange(setAlways({ tools, always }, t.name, e.target.checked))} />
                  A person approves every use of {t.name}</label>)}
            </div>))}
        </fieldset>))}
      {loose.length > 0 && (
        <p role="alert" className="rounded-lg border border-[var(--warn)] p-2 text-xs text-[var(--warn)]">
          {loose.join(", ")} change{loose.length === 1 ? "s" : ""} things and will run without a person's OK. Tick the box under it to make a person approve every use.</p>)}
    </>
  );
}
