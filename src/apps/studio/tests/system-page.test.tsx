import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "@northcx/api-client";
import SystemHealth from "../app/system/page";

vi.mock("@northcx/api-client", async (orig) => ({ ...(await orig<typeof client>()), systemHealth: vi.fn() }));
const api = vi.mocked(client);
afterEach(cleanup);

const ok = { name: "Database", status: "ok" as const, detail: "Postgres answers.", action: "" };
const failing = { name: "Database schema", status: "failing" as const, detail: "At revision 0057; this version expects 0058.", action: "Restart the server so the migrations run." };
const off = { name: "Channel: SMS", status: "not_set_up" as const, detail: "Not set up.", action: "Optional. See the channel's setting in .env.example if you want SMS." };

describe("System health page", () => {
  it("says everything is working when nothing is failing, and shows what is not set up as such", async () => {
    api.systemHealth.mockResolvedValue({ status: "ok", checks: [ok, off] });
    render(<SystemHealth />);
    expect(await screen.findByText("Everything that is set up is working.")).toBeTruthy();
    expect(screen.getByText("Working")).toBeTruthy();
    expect(screen.getByText("Not set up")).toBeTruthy();
  });

  it("names what is failing and says what to do for each", async () => {
    api.systemHealth.mockResolvedValue({ status: "failing", checks: [ok, failing, off] });
    render(<SystemHealth />);
    expect(await screen.findByText("1 thing is not working: Database schema.")).toBeTruthy();
    expect(screen.getByText("Not working")).toBeTruthy();
    expect(screen.getByText("What to do: Restart the server so the migrations run.")).toBeTruthy();
    expect(screen.queryByText(/What to do: .*Postgres/)).toBeNull();                 // a working check has no instruction
  });

  it("says how many things are failing when there are several", async () => {
    api.systemHealth.mockResolvedValue({ status: "failing", checks: [failing, { ...failing, name: "Alert delivery" }] });
    render(<SystemHealth />);
    expect(await screen.findByText("2 things are not working: Database schema, Alert delivery.")).toBeTruthy();
  });

  it("shows the error and a way to retry when the health route cannot be read", async () => {
    api.systemHealth.mockRejectedValue(new Error("403 forbidden"));
    render(<SystemHealth />);
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
