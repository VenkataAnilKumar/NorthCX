export type Status = "completed" | "escalated" | "needs_approval" | "unknown";

export interface TraceEvent { t: number; type: string; data: Record<string, unknown> }
export interface Trace { id: string; agent_id: string; session_id: string; events: TraceEvent[] }
export interface TraceSummary { id: string; agentId: string; sessionId: string; events: number; status: Status; startedAt: number | null; tools: string[] }
export interface Approval { id: string; trace_id: string; session_id: string; tool: string; input: unknown; reason: string; state: "pending" | "approved" | "rejected"; created_at: number; decided_by: string | null; decided_at: number | null }
export interface AgentInfo { id: string; instructions: string; model: string | null; maxSteps: number; tools: { name: string; description: string; approval: boolean }[]; guardrails: string[]; inputGuardrails: string[] }
export interface ChatReply { reply: string; status: Status; traceId: string; pendingApprovals: { id: string; tool: string; reason: string }[] }

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
export const decideApproval = (id: string, approved: boolean, by: string) =>
  api<Approval>(`/v1/approvals/${id}/decision`, { method: "POST", body: JSON.stringify({ approved, by }) });
export const listAgents = () => api<{ agents: AgentInfo[] }>("/v1/agents").then((r) => r.agents);
export const chat = (agentId: string, sessionId: string, message: string) =>
  api<ChatReply>(`/v1/agents/${agentId}/chat`, { method: "POST", body: JSON.stringify({ sessionId, message }) });

export const statusLabel: Record<string, string> = {
  completed: "Completed", escalated: "Escalated", needs_approval: "Needs approval", unknown: "Unknown",
};

export function formatTime(t: number | null | undefined): string {
  return t ? new Date(t * 1000).toLocaleString() : "";
}
