import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "@northcx/api-client";
import Connections from "../app/connections/page";

vi.mock("@northcx/api-client", async (orig) => ({ ...(await orig<typeof client>()), listConnections: vi.fn(), createConnection: vi.fn(), updateConnection: vi.fn(), deleteConnection: vi.fn(),
  reviewConnection: vi.fn(), approveConnectionTools: vi.fn(), checkConnection: vi.fn(), useMe: vi.fn() }));
const api = vi.mocked(client);

const shop: client.Connection = { id: "c1", name: "shop", url: "https://mcp.example.com/mcp", host: "mcp.example.com", trusted: false, secret: "orders", enabled: true,
  approvedTools: ["shop__orders_lookup"], createdBy: "ann", createdAt: 1, updatedBy: "ann", updatedAt: 1 };
const lookup: client.ConnectionTool = { name: "shop__orders_lookup", serverName: "orders_lookup", description: "Look up an order.", inputs: ["order_id"], access: "reads", fingerprint: "fp-1", approved: true };
const refund: client.ConnectionTool = { name: "shop__orders_refund", serverName: "orders_refund", description: "Refund an order.", inputs: ["order_id", "amount"], access: "changes", fingerprint: "fp-2", approved: false };

function as(role: "admin" | "viewer", connections = [shop], hosts = ["mcp.example.com"]) {
  api.useMe.mockReturnValue({ me: null, failed: false, can: (p: string) => role === "admin" || p !== "keys:manage", askForName: false });
  api.listConnections.mockResolvedValue({ connections, allowedHosts: hosts });
}
const click = (name: string | RegExp) => fireEvent.click(screen.getByRole("button", { name }));

beforeEach(() => { vi.clearAllMocks(); });
afterEach(cleanup);

describe("connections screen", () => {
  it("shows an administrator the allowed hosts, the add form and each connection's state in words", async () => {
    as("admin");
    render(<Connections />);
    expect(await screen.findByText("mcp.example.com", { selector: "p" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Add a connection" })).toBeTruthy();
    expect(screen.getByText(/shop/, { selector: "h2, h3" })).toBeTruthy();
    expect(screen.getByText("On")).toBeTruthy();
    expect(screen.getByText("Not trusted")).toBeTruthy();
    expect(screen.getByText(/1 tool approved/)).toBeTruthy();
  });

  it("shows someone who may not manage connections the list but no form and no buttons", async () => {
    as("viewer");
    render(<Connections />);
    await screen.findByText(/1 tool approved/);
    expect(screen.queryByRole("heading", { name: "Add a connection" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Switch off" })).toBeNull();
  });

  it("explains what to do when no host is allowed instead of showing a form that cannot work", async () => {
    as("admin", [], []);
    render(<Connections />);
    expect(await screen.findByText(/Ask the person who runs NorthCX to set NORTHCX_MCP_HOSTS/)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Add a connection" })).toBeNull();
    expect(screen.getByText("No connections yet.")).toBeTruthy();
  });

  it("adds a connection from the form with labelled fields and shows the server's message when it is refused", async () => {
    as("admin", []);
    api.createConnection.mockRejectedValueOnce(new Error("The host 'x' is not on the allowed list for MCP servers. Ask the operator to add it if the server is trusted."));
    render(<Connections />);
    fireEvent.change(await screen.findByLabelText(/^Name/), { target: { value: "shop" } });
    fireEvent.change(screen.getByLabelText(/^Address/), { target: { value: "https://x.example.com/mcp" } });
    click("Add connection");
    expect(await screen.findByText(/not on the allowed list/)).toBeTruthy();
    api.createConnection.mockResolvedValueOnce(shop);
    fireEvent.change(screen.getByLabelText(/^Credential/), { target: { value: "orders" } });
    fireEvent.click(screen.getByLabelText(/I trust this server/));
    click("Add connection");
    await waitFor(() => expect(api.createConnection).toHaveBeenLastCalledWith({ name: "shop", url: "https://x.example.com/mcp", secret: "orders", trusted: true }));
  });

  it("reviews the tools, says which can change things, and approves only the ticked ones with the fingerprints it was shown", async () => {
    as("admin");
    api.reviewConnection.mockResolvedValue({ tools: [lookup, refund], skipped: [{ name: "poisoned", reason: "its description or input fields contain instructions to the model" }] });
    api.approveConnectionTools.mockResolvedValue({ ...shop, approvedTools: ["shop__orders_lookup", "shop__orders_refund"] });
    render(<Connections />);
    await screen.findByText(/1 tool approved/);
    click("Tools");
    click("Review the tools");
    const group = await screen.findByRole("group", { name: "Tools agents may use" });
    expect(within(group).getByText("Only reads")).toBeTruthy();
    expect(within(group).getByText(/Can change things: waits for a person/)).toBeTruthy();
    expect((within(group).getByLabelText(/shop__orders_lookup/) as HTMLInputElement).checked).toBe(true);  // already approved
    expect((within(group).getByLabelText(/shop__orders_refund/) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText(/poisoned: its description or input fields contain instructions/)).toBeTruthy();
    fireEvent.click(within(group).getByLabelText(/shop__orders_refund/));
    click("Approve the ticked tools");
    await waitFor(() => expect(api.approveConnectionTools).toHaveBeenCalledWith("c1", { shop__orders_lookup: "fp-1", shop__orders_refund: "fp-2" }));
    expect((await screen.findByRole("status")).textContent).toContain("2 tools are approved");
  });

  it("shows the refusal and looks again when a tool changed between the review and the approval", async () => {
    as("admin");
    api.reviewConnection.mockResolvedValue({ tools: [lookup], skipped: [] });
    api.approveConnectionTools.mockRejectedValue(new Error("'shop__orders_lookup' changed since you looked at it. Review the tools again before approving."));
    render(<Connections />);
    await screen.findByText(/1 tool approved/);
    click("Tools");
    click("Review the tools");
    await screen.findByRole("group", { name: "Tools agents may use" });
    click("Approve the ticked tools");
    expect(await screen.findByText(/changed since you looked at it/)).toBeTruthy();
    await waitFor(() => expect(api.reviewConnection).toHaveBeenCalledTimes(2));
  });

  it("reports a check in plain words: changed, new, removed, nothing, or no answer", async () => {
    as("admin");
    render(<Connections />);
    await screen.findByText(/1 tool approved/);
    api.checkConnection.mockResolvedValueOnce({ reachable: true, message: null, added: ["shop__orders_export"], changed: ["shop__orders_lookup"], removed: ["shop__orders_refund"] });
    click("Check for changes");
    const result = await screen.findByRole("status");
    expect(result.textContent).toContain("switched off until you review and approve them again: shop__orders_lookup");
    expect(result.textContent).toContain("not usable until you approve them: shop__orders_export");
    expect(result.textContent).toContain("no longer offers: shop__orders_refund");
    api.checkConnection.mockResolvedValueOnce({ reachable: true, message: null, added: [], changed: [], removed: [] });
    click("Check for changes");
    await screen.findByText("Nothing has changed since you approved the tools.");
    api.checkConnection.mockResolvedValueOnce({ reachable: false, message: "The shop system did not answer in time.", added: [], changed: [], removed: [] });
    click("Check for changes");
    await screen.findByText(/The server did not answer: The shop system did not answer in time/);
  });

  it("switches a connection off and back on, changes trust, and asks twice before deleting", async () => {
    as("admin");
    api.updateConnection.mockResolvedValue(shop);
    api.deleteConnection.mockResolvedValue({ deleted: true });
    render(<Connections />);
    await screen.findByText(/1 tool approved/);
    click("Switch off");
    await waitFor(() => expect(api.updateConnection).toHaveBeenCalledWith("c1", { enabled: false }));
    click("Trust this server");
    await waitFor(() => expect(api.updateConnection).toHaveBeenCalledWith("c1", { trusted: true }));
    click("Delete");
    expect(api.deleteConnection).not.toHaveBeenCalled();
    click("Yes, delete shop");
    await waitFor(() => expect(api.deleteConnection).toHaveBeenCalledWith("c1"));
  });

  it("says a switched-off connection also stops conversations that are already running", async () => {
    as("admin", [{ ...shop, enabled: false }]);
    render(<Connections />);
    expect(await screen.findByText(/including in conversations that are already running/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Switch on" })).toBeTruthy();
  });

  it("shows the server's plain message when the list cannot be loaded", async () => {
    api.useMe.mockReturnValue({ me: null, failed: false, can: () => true, askForName: false });
    api.listConnections.mockRejectedValue(new Error("MCP connections are not configured on this server"));
    render(<Connections />);
    expect(await screen.findByText(/MCP connections are not configured on this server/)).toBeTruthy();
  });
});

describe("api client for connections", () => {
  it("calls the connection routes with the right methods and bodies", async () => {
    const real = await vi.importActual<typeof client>("@northcx/api-client");
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await real.createConnection({ name: "shop", url: "https://x.example.com/mcp", trusted: false });
    await real.updateConnection("c1", { enabled: false });
    await real.reviewConnection("c1");
    await real.approveConnectionTools("c1", { a: "fp" });
    await real.checkConnection("c1");
    await real.deleteConnection("c1");
    const calls = fetchMock.mock.calls.map(([url, init]) => [init.method ?? "GET", url, init.body ?? null]);
    expect(calls).toEqual([
      ["POST", "/api/northcx/v1/connections", JSON.stringify({ name: "shop", url: "https://x.example.com/mcp", trusted: false })],
      ["PUT", "/api/northcx/v1/connections/c1", JSON.stringify({ enabled: false })],
      ["POST", "/api/northcx/v1/connections/c1/review", null],
      ["POST", "/api/northcx/v1/connections/c1/approve", JSON.stringify({ tools: { a: "fp" } })],
      ["POST", "/api/northcx/v1/connections/c1/check", null],
      ["DELETE", "/api/northcx/v1/connections/c1", null],
    ]);
    vi.unstubAllGlobals();
  });
});
