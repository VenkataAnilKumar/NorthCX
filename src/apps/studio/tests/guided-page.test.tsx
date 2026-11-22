import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "@northcx/api-client";
import Guided from "../app/guided/page";

let query = "agent=support";
const push = vi.fn();
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(query), useRouter: () => ({ push }) }));
vi.mock("@northcx/api-client", async (orig) => ({ ...(await orig<typeof client>()), getLive: vi.fn(), getCatalog: vi.fn(), previewSpec: vi.fn(), saveSpec: vi.fn(), listAgents: vi.fn(), useMe: vi.fn() }));
const api = vi.mocked(client);

const catalog = { tools: [
  { name: "lookup_order", description: "Look up an order.", effect: "read", audience: "customer", source: "registry", connection: null, fingerprint: "a", approval: false, inputs: [] },
  { name: "issue_refund", description: "Refund an order.", effect: "write", audience: "customer", source: "registry", connection: null, fingerprint: "b", approval: true, inputs: [] }],
  guardrails: [], inputGuardrails: [], outputGuardrails: [], skills: [], flexibility: [] } as unknown as client.Catalog;
const valid = (summary: string[]) => ({ valid: true, problems: [], summary, unchangedSinceLatest: false });

function setup(spec: Record<string, unknown> = { id: "support", instructions: "" }, can = true) {
  api.useMe.mockReturnValue({ me: null, failed: false, can: () => can, askForName: false });
  api.getLive.mockResolvedValue({ spec, digest: "d1" } as never);
  api.getCatalog.mockResolvedValue(catalog);
  api.previewSpec.mockImplementation(async (_id, s) => valid([`This agent answers customers.`, `Tools: ${(s as { tools?: string[] }).tools?.join(", ") ?? "none"}`]));
  api.saveSpec.mockResolvedValue({ number: 4 } as never);
  render(<Guided />);
}
const step = (n: number) => within(screen.getByRole("list", { name: "Steps" })).getAllByRole("listitem")[n - 1];
beforeEach(() => { vi.clearAllMocks(); query = "agent=support"; });
afterEach(cleanup);

describe("guided setup", () => {
  it("offers a choice of agent, a template or your own material when none is chosen", async () => {
    query = "";
    api.useMe.mockReturnValue({ me: null, failed: false, can: () => true, askForName: false });
    api.listAgents.mockResolvedValue([{ id: "support" }] as never);
    render(<Guided />);
    fireEvent.change(await screen.findByLabelText("Agent"), { target: { value: "support" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(push).toHaveBeenCalledWith("/guided?agent=support");
    expect(screen.getByRole("link", { name: "Start from a template" }).getAttribute("href")).toBe("/hub");
    expect(screen.getByRole("link", { name: "Start from my own material" }).getAttribute("href")).toBe("/agents/build");
  });

  it("holds one step as next at a time and moves on as the author does each thing", async () => {
    setup();
    await screen.findByLabelText("Instructions");
    expect(step(2).getAttribute("aria-current")).toBe("step");
    expect(within(step(3)).getByText("Waiting")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("This agent does not need any tools"));
    expect(step(3).getAttribute("aria-current")).toBe("step");
    fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "Help customers with their orders." } });
    await waitFor(() => expect(step(5).getAttribute("aria-current")).toBe("step"));
    expect(within(step(4)).getByText("Done")).toBeTruthy();
  });

  it("offers a customer agent only customer tools and a staff agent only staff tools", async () => {
    catalog.tools.push({ name: "list_handoffs", description: "List hand-offs.", effect: "read", audience: "staff", source: "staff", connection: null, fingerprint: "c", approval: false, inputs: [] } as never);
    setup({ id: "support", instructions: "Help." });
    await screen.findByLabelText(/lookup_order/, { selector: "input" });
    expect(screen.queryByLabelText(/list_handoffs/, { selector: "input" })).toBeNull();
    cleanup();
    setup({ id: "helper", instructions: "Help.", audience: "staff" });
    expect(await screen.findByLabelText(/list_handoffs/, { selector: "input" })).toBeTruthy();
    expect(screen.queryByLabelText(/lookup_order/, { selector: "input" })).toBeNull();
    catalog.tools.pop();
  });

  it("makes a tool that changes things need a person's OK as it is added, and says what the agent will do", async () => {
    setup({ id: "support", instructions: "Help." });
    fireEvent.click(await screen.findByLabelText(/issue_refund/, { selector: "input" }));
    expect((screen.getByLabelText("A person approves every use of issue_refund") as HTMLInputElement).checked).toBe(true);
    await waitFor(() => expect(api.previewSpec).toHaveBeenLastCalledWith("support", expect.objectContaining({ tools: ["issue_refund"], approvals: { always: ["issue_refund"] } })));
    expect(await screen.findByText("Tools: issue_refund")).toBeTruthy();
  });

  it("shows the problems in plain words instead of the summary and does not allow saving", async () => {
    setup({ id: "support", instructions: "Help." });
    api.previewSpec.mockResolvedValue({ valid: false, problems: ["The tool 'nope' does not exist here. Pick one from the list or remove it."] });
    fireEvent.click(await screen.findByLabelText("This agent does not need any tools"));
    expect(await screen.findByText("Fix these first:")).toBeTruthy();
    expect(screen.getByText(/The tool 'nope' does not exist here/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Save a version" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("saves a version and points to the tests and release, and asks for a new save after a change", async () => {
    setup({ id: "support", instructions: "Help." });
    fireEvent.click(await screen.findByLabelText("This agent does not need any tools"));
    const save = await screen.findByRole("button", { name: "Save a version" });
    await waitFor(() => expect((save as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(save);
    expect((await screen.findByRole("status")).textContent).toContain("Saved as version 4");
    expect(screen.getByRole("link", { name: /Run its tests and release it/ }).getAttribute("href")).toBe("/agents/support");
    fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "Help, kindly." } });
    expect(screen.queryByRole("link", { name: /Run its tests and release it/ })).toBeNull();
  });

  it("lets someone who may not change agents look but not save", async () => {
    setup({ id: "support", instructions: "Help." }, false);
    expect((await screen.findByLabelText("Instructions")).matches(":disabled")).toBe(true);
    expect(screen.getByText(/Your role can look but not change/)).toBeTruthy();
  });
});
