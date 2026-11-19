import type { CatalogTool } from "@northcx/api-client";

const SOURCE_TITLES: Record<string, string> = {
  registry: "Built in", connectors: "Connectors", verification: "Verification", knowledge: "Knowledge", memory: "Memory", staff: "Staff tools",
};

/** The tool picker's sections: one per MCP connection, one per other source. Order is stable: built in first, then the rest by title. */
export function toolGroups(tools: CatalogTool[]): { title: string; tools: CatalogTool[] }[] {
  const groups = new Map<string, CatalogTool[]>();
  for (const t of tools) {
    const title = t.connection ? `Connection: ${t.connection}` : SOURCE_TITLES[t.source] ?? t.source;
    groups.set(title, [...(groups.get(title) ?? []), t]);
  }
  return [...groups].map(([title, list]) => ({ title, tools: list })).sort((a, b) => Number(b.title === "Built in") - Number(a.title === "Built in") || a.title.localeCompare(b.title));
}
