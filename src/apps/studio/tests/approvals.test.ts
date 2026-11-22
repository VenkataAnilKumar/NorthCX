import { describe, expect, it } from "vitest";
import { chooseTool, setAlways, unguarded } from "../lib/approvals";

const none = { tools: [], always: [] as string[] };

describe("chooseTool", () => {
  it("makes a tool that changes things need a person's OK as soon as it is added, and a read-only tool not", () => {
    expect(chooseTool(none, "issue_refund", true, true)).toEqual({ tools: ["issue_refund"], always: ["issue_refund"] });
    expect(chooseTool(none, "lookup_order", true, false)).toEqual({ tools: ["lookup_order"], always: [] });
  });
  it("takes the tool and its OK rule away together", () => {
    expect(chooseTool({ tools: ["issue_refund", "lookup_order"], always: ["issue_refund"] }, "issue_refund", false, true)).toEqual({ tools: ["lookup_order"], always: [] });
  });
  it("does not add a tool twice or undo an author's choice when it is added again", () => {
    const kept = { tools: ["issue_refund"], always: [] as string[] };           // the author switched the OK rule off
    expect(chooseTool(kept, "issue_refund", true, true)).toBe(kept);
  });
});

describe("setAlways and unguarded", () => {
  const catalog = [{ name: "issue_refund", effect: "write" }, { name: "lookup_order", effect: "read" }];
  it("switches the rule on and off for one tool", () => {
    const on = setAlways({ tools: ["issue_refund"], always: [] }, "issue_refund", true);
    expect(on.always).toEqual(["issue_refund"]);
    expect(setAlways(on, "issue_refund", false).always).toEqual([]);
  });
  it("lists the tools that change things and will run without a person", () => {
    expect(unguarded({ tools: ["issue_refund", "lookup_order"], always: [] }, catalog)).toEqual(["issue_refund"]);
    expect(unguarded({ tools: ["issue_refund", "lookup_order"], always: ["issue_refund"] }, catalog)).toEqual([]);
  });
  it("does not warn about a tool that has a rule of its own", () => {
    expect(unguarded({ tools: ["issue_refund"], always: [] }, [{ name: "issue_refund", effect: "write", approval: true }])).toEqual([]);
  });
});
