export type Status = "completed" | "escalated" | "needs_approval" | "unknown";

export interface TraceEvent { t: number; type: string; data: Record<string, unknown> }
export interface Trace { id: string; agent_id: string; session_id: string; events: TraceEvent[] }
export interface TraceSummary { id: string; agentId: string; sessionId: string; events: number; status: Status; startedAt: number | null; tools: string[] }
export type ApprovalState = "pending" | "approved" | "rejected" | "expired" | "executing" | "executed" | "failed";
export interface Approval { id: string; trace_id: string; session_id: string; tool: string; input: unknown; reason: string; state: ApprovalState; created_at: number; decided_by: string | null; decided_at: number | null; note: string | null; result: unknown }
export interface Resume { reply?: string; status?: Status; traceId?: string; error?: string }
export interface OutboxMessage { id: number; kind: string; createdAt: number; reply: string; status: Status; traceId: string; tool?: string; approved?: boolean }
export interface AgentInfo { id: string; instructions: string; model: string | null; maxSteps: number; tools: { name: string; description: string; approval: boolean }[]; guardrails: string[]; inputGuardrails: string[] }
export interface ChatReply { reply: string; status: Status; traceId: string; pendingApprovals: { id: string; tool: string; reason: string }[]; handoffId: string | null }
export interface HandoffSummary { id: string; sessionId: string; traceId: string; agentId: string; customerId: string | null; trigger: string; reason: string; topics: string[]; state: "open" | "resolved"; createdAt: number; resolvedBy: string | null; resolvedAt: number | null; note: string | null; summary: string }
export interface HandoffPackage { summary: string; trigger: string; triggerDescription: string; reason: string; topics: string[]; transcript: { from: "customer" | "agent" | "platform"; text: string }[]; customerFacts: Record<string, string>; actions: { tool: string; input: unknown; outcome: string; detail: unknown; traceId: string }[]; approvals: { id: string; tool: string; state: string; reason: string; input: unknown; note: string | null }[] }
export interface Handoff extends HandoffSummary { package: HandoffPackage }

const KEY = "northcx.apiKey";

export function getApiKey(): string {
  try { return sessionStorage.getItem(KEY) ?? ""; } catch { return ""; }
}
export function setApiKey(key: string): void {
  try { key ? sessionStorage.setItem(KEY, key) : sessionStorage.removeItem(KEY); } catch { /* storage unavailable */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const key = getApiKey();
  if (key) headers.set("authorization", `Bearer ${key}`);
  if (init.body) headers.set("content-type", "application/json");
  const res = await fetch(`/api/northcx${path}`, { ...init, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body?.error?.message ?? `Request failed (${res.status})`);
  return body as T;
}

export const listTraces = (status?: string) =>
  api<{ traces: TraceSummary[] }>("/v1/traces").then((r) => (status ? r.traces.filter((t) => t.status === status) : r.traces));
export const getTrace = (id: string) => api<Trace>(`/v1/traces/${id}`);
export const listApprovals = (state?: string) => api<{ approvals: Approval[] }>(`/v1/approvals${state ? `?state=${state}` : ""}`).then((r) => r.approvals);
export const decideApproval = (id: string, approved: boolean, by: string, note?: string) =>
  api<Approval & { resume: Resume | null }>(`/v1/approvals/${id}/decision`, { method: "POST", body: JSON.stringify({ approved, by, ...(note ? { note } : {}) }) });
export const listHandoffs = (state?: string) => api<{ handoffs: HandoffSummary[] }>(`/v1/handoffs${state ? `?state=${state}` : ""}`).then((r) => r.handoffs);
export const getHandoff = (id: string) => api<Handoff>(`/v1/handoffs/${id}`);
export const resolveHandoff = (id: string, by: string, note?: string) =>
  api<HandoffSummary>(`/v1/handoffs/${id}/resolve`, { method: "POST", body: JSON.stringify({ by, ...(note ? { note } : {}) }) });
export interface SimScenario { name: string; agent: string; required: boolean; description: string; steps: number; judge: boolean; digest: string }
export interface SimFailure { where: string; check: string; expected: unknown; actual: unknown }
export interface SimScenarioResult { name: string; required: boolean; passed: boolean; pass_rate: number; agent: string; notes: string[]; trials: { failures: SimFailure[] }[] }
export interface SimRunSummary { id: string; createdAt: number; mode: string; source: string; passed: boolean; counts: { total: number; passed: number; failed: number; required_failed: number }; seconds: number; meta: Record<string, string>; agentDigests: Record<string, string> }
export interface SimRunDetail extends SimRunSummary { results: SimScenarioResult[] }
export interface Gate { agent: string; agentDigest: string | null; satisfied: boolean; required: number; covered: number; reasons: string[]; runIds: string[] }
export const listSimScenarios = () => api<{ modes: string[]; scenarios: SimScenario[] }>("/v1/simulations/scenarios");
export const listSimRuns = () => api<{ runs: SimRunSummary[] }>("/v1/simulations/runs").then((r) => r.runs);
export const getSimRun = (id: string) => api<SimRunDetail>(`/v1/simulations/runs/${id}`);
export const getGates = () => api<{ gates: Gate[] }>("/v1/simulations/gate").then((r) => r.gates);
export const runSimulation = (mode: string, skipJudge: boolean, only?: string) =>
  api<SimRunSummary>("/v1/simulations/runs", { method: "POST", body: JSON.stringify({ mode, skipJudge, ...(only ? { only } : {}) }) });
export const listOutbox = (sessionId: string, after: number) =>
  api<{ messages: OutboxMessage[] }>(`/v1/sessions/${encodeURIComponent(sessionId)}/outbox?after=${after}`).then((r) => r.messages);
export const listAgents = () => api<{ agents: AgentInfo[] }>("/v1/agents").then((r) => r.agents);
export const chat = (agentId: string, sessionId: string, message: string) =>
  api<ChatReply>(`/v1/agents/${agentId}/chat`, { method: "POST", body: JSON.stringify({ sessionId, message }) });

export const statusLabel: Record<string, string> = {
  completed: "Completed", escalated: "Escalated", needs_approval: "Needs approval", unknown: "Unknown",
};

export function formatTime(t: number | null | undefined): string {
  return t ? new Date(t * 1000).toLocaleString() : "";
}
