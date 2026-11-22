import { describe, expect, it } from "vitest";
import type { CatalogTool } from "@northcx/api-client";
import { toolGroups } from "../lib/tool-groups";

const t = (name: string, source: string, connection: string | null = null): CatalogTool =>
  ({ name, description: "", effect: "read", audience: "customer", source, connection, fingerprint: "f", approval: false, inputs: [] });

describe("toolGroups", () => {
  it("puts built-in tools first, then one section per connection and source, each tool once", () => {
    const groups = toolGroups([t("shop__a", "mcp", "shop"), t("crm_find", "connectors"), t("lookup", "registry"), t("shop__b", "mcp", "shop"), t("recall", "memory")]);
    expect(groups.map((g) => g.title)).toEqual(["Built in", "Connection: shop", "Connectors", "Memory"]);
    expect(groups[1].tools.map((x) => x.name)).toEqual(["shop__a", "shop__b"]);
  });
  it("shows an unknown source under its own name instead of hiding its tools", () => {
    expect(toolGroups([t("x", "newkind")]).map((g) => g.title)).toEqual(["newkind"]);
  });
});
