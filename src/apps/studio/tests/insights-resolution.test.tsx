import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "@northcx/api-client";
import Insights from "../app/insights/page";

vi.mock("@northcx/api-client", async (orig) => ({ ...(await orig<typeof client>()), getOverview: vi.fn(), getSeries: vi.fn(), getFailures: vi.fn(), getGaps: vi.fn(), getAlerts: vi.fn(), getReviewQuality: vi.fn() }));
afterEach(cleanup);

const ratio = (n: number, d: number) => ({ value: d ? n / d : null, numerator: n, denominator: d });
const overview = (firm?: unknown) => ({
  period: { from: 0, to: 1 }, conversations: 10, turns: 10, containmentRate: ratio(9, 10), resolutionRate: { ...ratio(8, 10), pending: 1, windowDays: 3, provisional: true }, ...(firm ? { resolutionFirm: firm } : {}),
  escalationRate: ratio(1, 10), approvalRate: ratio(0, 10), guardrailBlockRate: ratio(0, 10), toolErrorRate: ratio(0, 5), errorRate: ratio(0, 10), fallbackModelRate: ratio(0, 10),
  latencySeconds: { p50: 1, p95: 2, samples: 10 }, tokens: { total: 100, perConversation: 10, modelCalls: 10 }, handoffs: { total: 1, byTrigger: {}, byQueue: {}, byTopic: {} },
  tools: { used: {}, errors: {} }, guardrails: {}, satisfaction: { average: null, responses: 0, responseRate: ratio(0, 10), distribution: {} }, note: "", agent: null, environment: "production", truncated: false,
});

function setup(o: unknown) {
  const api = vi.mocked(client);
  api.getOverview.mockResolvedValue(o as never);
  api.getSeries.mockResolvedValue({ bucket: "day", points: [] } as never);
  api.getFailures.mockResolvedValue([] as never);
  api.getGaps.mockResolvedValue({ unansweredSearches: [], messagesBeforeHandoff: [] } as never);
  api.getAlerts.mockResolvedValue({ enabled: false, rules: [], active: [], recent: [], webhook: false, undelivered: 0, lastRun: null } as never);
  api.getReviewQuality.mockResolvedValue({ reviewed: 0, correctRate: ratio(0, 0), escalationCorrectness: ratio(0, 0), unneededEscalationRate: ratio(0, 0), failuresByKind: {}, note: "" } as never);
}

describe("the insights page shows both resolution figures", () => {
  it("shows the old figure and the one that counts returns, each with its own count, and says how far the second can be trusted", async () => {
    setup(overview({ ...ratio(6, 10), reopened: 2, checkable: 4, windowDays: 3 }));
    render(<Insights />);
    expect(await screen.findByText("Resolved (provisional)")).toBeTruthy();
    expect(screen.getByText("Resolved, counting returns")).toBeTruthy();
    expect(screen.getByText(/6 of 10 · as above, but not when the same customer came back within 3 days \(2 did\); only 4 of 10 conversations have a known customer/)).toBeTruthy();
    expect(screen.getByText(/8 of 10 · completed, no hand-off/)).toBeTruthy();
  });

  it("shows only the old figure from a server that does not send the new one", async () => {
    setup(overview());
    render(<Insights />);
    expect(await screen.findByText("Resolved (provisional)")).toBeTruthy();
    expect(screen.queryByText("Resolved, counting returns")).toBeNull();
  });
});
