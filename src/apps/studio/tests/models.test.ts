import { describe, expect, it } from "vitest";
import type { ModelQualification, ModelsOverview } from "@northcx/api-client";
import { modelChoices, qualificationNote } from "@/lib/models";

const overview = { providers: [
  { name: "ollama", defaultModel: "qwen", tier: "local" },
  { name: "cloud", defaultModel: "big", tier: "public-cloud" },
  { name: "empty", defaultModel: null, tier: "local" },
] } as unknown as ModelsOverview;
const q = (o: Partial<ModelQualification>): ModelQualification => ({ agent: "a", model: "ollama:qwen", agentDigest: "d", qualified: true, required: { total: 4, passed: 4 }, other: { total: 0, passed: 0 }, runId: "r", createdAt: 1_700_000_000, reasons: [], ...o });

describe("model choices", () => {
  it("lists providers that name a model, with their tier", () => {
    const c = modelChoices(overview, "");
    expect(c.map((x) => x.value)).toEqual(["ollama:qwen", "cloud:big"]);
    expect(c[0].tier).toBe("Local (your servers)");
  });
  it("keeps a value that is no longer configured, without a tier", () => {
    expect(modelChoices(overview, "old:model").at(-1)).toEqual({ value: "old:model", label: "old:model", tier: null });
  });
});

describe("qualification note", () => {
  it("says not qualified yet when no run exists for that model", () => {
    expect(qualificationNote("cloud:big", [q({})], false)).toMatch(/^Not qualified yet/);
  });
  it("uses the latest run for that model", () => {
    const n = qualificationNote("ollama:qwen", [q({ createdAt: 1_600_000_000, qualified: false }), q({})], false);
    expect(n).toBe("Qualified on 2023-11-14: 4 of 4 required scenarios passed.");
  });
  it("gives the first reason when a model did not qualify", () => {
    const n = qualificationNote("ollama:qwen", [q({ qualified: false, required: { total: 4, passed: 2 }, reasons: ["required scenarios: 2 of 4 passed (need 100%)"] })], false);
    expect(n).toContain("Did not qualify");
    expect(n).toContain("2 of 4 required scenarios passed");
  });
  it("explains the default when the server requires qualification", () => {
    expect(qualificationNote("", [], true)).toMatch(/only after it passes/);
  });
});
