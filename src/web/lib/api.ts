export type Status = "completed" | "escalated" | "needs_approval" | "unknown";

export interface TraceEvent { t: number; type: string; data: Record<string, unknown> }
export interface Trace { id: string; agent_id: string; session_id: string; agent_version: number | null; events: TraceEvent[] }
export interface TraceSummary { id: string; agentId: string; sessionId: string; events: number; status: Status; startedAt: number | null; tools: string[]; agentVersion: number | null }
export type ApprovalState = "pending" | "approved" | "rejected" | "expired" | "executing" | "executed" | "failed";
export interface Approval { id: string; trace_id: string; session_id: string; tool: string; input: unknown; reason: string; state: ApprovalState; created_at: number; decided_by: string | null; decided_at: number | null; note: string | null; result: unknown }
export interface Resume { reply?: string; status?: Status; traceId?: string; error?: string }
export interface OutboxMessage { id: number; kind: string; createdAt: number; reply: string; status: Status; traceId: string; tool?: string; approved?: boolean }
export interface AgentInfo { id: string; version: number | null; digest: string | null; instructions: string; model: string | null; maxSteps: number; tools: { name: string; description: string; approval: boolean }[]; guardrails: string[]; inputGuardrails: string[] }
export interface ChatReply { reply: string; status: Status; traceId: string; pendingApprovals: { id: string; tool: string; reason: string }[]; handoffId: string | null; agentVersion: number | null }
export interface HandoffSummary { id: string; sessionId: string; traceId: string; agentId: string; customerId: string | null; trigger: string; reason: string; topics: string[]; state: "open" | "resolved"; createdAt: number; resolvedBy: string | null; resolvedAt: number | null; note: string | null; summary: string; queue?: string | null; afterHours?: boolean }
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
  constructor(public status: number, message: string, public reasons: string[] = []) { super(message); }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const key = getApiKey();
  if (key) headers.set("authorization", `Bearer ${key}`);
  if (init.body) headers.set("content-type", "application/json");
  const res = await fetch(`/api/northcx${path}`, { ...init, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body?.error?.message ?? `Request failed (${res.status})`, body?.error?.reasons ?? []);
  return body as T;
}

export const listTraces = (status?: string) =>
  api<{ traces: TraceSummary[] }>("/v1/traces").then((r) => (status ? r.traces.filter((t) => t.status === status) : r.traces));
export const getTrace = (id: string) => api<Trace>(`/v1/traces/${id}`);
export const listApprovals = (state?: string) => api<{ approvals: Approval[] }>(`/v1/approvals${state ? `?state=${state}` : ""}`).then((r) => r.approvals);
export const decideApproval = (id: string, approved: boolean, by?: string, note?: string) =>
  api<Approval & { resume: Resume | null }>(`/v1/approvals/${id}/decision`, { method: "POST", body: JSON.stringify({ approved, ...(by ? { by } : {}), ...(note ? { note } : {}) }) });
export const listHandoffs = (state?: string, queue?: string) => {
  const q = new URLSearchParams();
  if (state) q.set("state", state);
  if (queue) q.set("queue", queue);
  return api<{ handoffs: HandoffSummary[] }>(`/v1/handoffs${q.size ? `?${q}` : ""}`).then((r) => r.handoffs);
};
export interface RoutingQueue { name: string; open: boolean; nextOpen: number | null; topics: string[]; triggers: string[] }
export const getRouting = () => api<{ timezone: string; defaultQueue: string; holidays: string[]; queues: RoutingQueue[] }>("/v1/routing");
export const getHandoff = (id: string) => api<Handoff>(`/v1/handoffs/${id}`);
export const resolveHandoff = (id: string, by?: string, note?: string) =>
  api<HandoffSummary>(`/v1/handoffs/${id}/resolve`, { method: "POST", body: JSON.stringify({ ...(by ? { by } : {}), ...(note ? { note } : {}) }) });
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
export interface AgentVersion { id: string; agentId: string; number: number; digest: string; author: string; note: string | null; createdAt: number; live: boolean; everReleased: boolean; spec?: unknown; specYaml?: string }
export interface ReleaseRecord { id: string; agentId: string; environment: string; action: "publish" | "rollback"; version: number | null; previousVersion: number | null; by: string; note: string | null; gate: { satisfied?: boolean; covered?: number; required?: number }; createdAt: number; toBaseline: boolean }
export interface LiveInfo { agentId: string; source: "release" | "baseline"; version: number | null; digest: string; release: ReleaseRecord | null; specYaml: string }
export interface VersionDiff { from: number; to: number; identical: boolean; instructions: string | null; tools: { added: string[]; removed: string[] }; guardrails: Chg; input_guardrails: Chg; forced_handoff: Chg; other: Record<string, { from: unknown; to: unknown }> }
interface Chg { added: string[]; removed: string[]; changed: string[] }
const agentPath = (id: string) => `/v1/agents/${encodeURIComponent(id)}`;
export const getLive = (id: string) => api<LiveInfo>(`${agentPath(id)}/live`);
export const listVersions = (id: string) => api<{ versions: AgentVersion[] }>(`${agentPath(id)}/versions`).then((r) => r.versions);
export const getVersionDetail = (id: string, n: number) => api<AgentVersion>(`${agentPath(id)}/versions/${n}`);
export const createVersion = (id: string, specYaml: string, by?: string, note?: string) =>
  api<AgentVersion>(`${agentPath(id)}/versions`, { method: "POST", body: JSON.stringify({ specYaml, ...(by ? { by } : {}), ...(note ? { note } : {}) }) });
export const diffVersions = (id: string, a: number, b: number) => api<VersionDiff>(`${agentPath(id)}/versions/${a}/diff/${b}`);
export const versionGate = (id: string, n: number) =>
  api<{ gates: Gate[] }>(`/v1/simulations/gate?agent=${encodeURIComponent(id)}&version=${n}`).then((r) => r.gates[0]);
export const runForVersion = (id: string, n: number) =>
  api<SimRunSummary>("/v1/simulations/runs", { method: "POST", body: JSON.stringify({ mode: "scripted", skipJudge: true, agent: id, version: n }) });
export const publishVersion = (id: string, version: number, by?: string, note?: string) =>
  api<ReleaseRecord>(`${agentPath(id)}/releases`, { method: "POST", body: JSON.stringify({ version, ...(by ? { by } : {}), ...(note ? { note } : {}) }) });
export const rollbackAgent = (id: string, by?: string, note?: string) =>
  api<ReleaseRecord>(`${agentPath(id)}/rollback`, { method: "POST", body: JSON.stringify({ ...(by ? { by } : {}), ...(note ? { note } : {}) }) });
export const listReleases = (id: string) => api<{ releases: ReleaseRecord[] }>(`${agentPath(id)}/releases`).then((r) => r.releases);
export interface Me { name: string; role: string; openMode: boolean; keyId: string | null; permissions: string[] }
export interface KeyInfo { id: string; prefix: string; name: string; role: string; createdBy: string; createdAt: number; expiresAt: number | null; revokedAt: number | null; revokedBy: string | null; lastUsedAt: number | null; active: boolean }
export interface AuditEntry { id: number; at: number; actor: string; role: string; keyId: string | null; action: string; target: string; outcome: string; detail: Record<string, unknown> }
export const getMe = () => api<Me>("/v1/me");
export const listKeys = () => api<{ roles: Record<string, string[]>; keys: KeyInfo[] }>("/v1/keys");
export const createKey = (name: string, role: string, expiresInDays?: number) =>
  api<KeyInfo & { key: string }>("/v1/keys", { method: "POST", body: JSON.stringify({ name, role, ...(expiresInDays ? { expiresInDays } : {}) }) });
export const revokeKey = (id: string) => api<KeyInfo>(`/v1/keys/${id}/revoke`, { method: "POST" });
export const listAudit = (action?: string, actor?: string, before?: number) => {
  const q = new URLSearchParams({ limit: "100" });
  if (action) q.set("action", action);
  if (actor) q.set("actor_name", actor);
  if (before) q.set("before", String(before));
  return api<{ entries: AuditEntry[] }>(`/v1/audit?${q}`).then((r) => r.entries);
};
export const verifyAudit = () => api<{ ok: boolean; checked: number; brokenAt: number | null; reason: string | null; head: string | null }>("/v1/audit/verify");
export const listOutbox = (sessionId: string, after: number) =>
  api<{ messages: OutboxMessage[] }>(`/v1/sessions/${encodeURIComponent(sessionId)}/outbox?after=${after}`).then((r) => r.messages);
export const listAgents = () => api<{ agents: AgentInfo[] }>("/v1/agents").then((r) => r.agents);
export const chat = (agentId: string, sessionId: string, message: string) =>
  api<ChatReply>(`/v1/agents/${agentId}/chat`, { method: "POST", body: JSON.stringify({ sessionId, message }) });

export interface StreamHandlers { onProgress?: (tool: string) => void; onDelta?: (text: string) => void }

/** Splits a server-sent-event stream into [event, data] pairs; handles events split across network chunks. */
export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<[string, unknown]> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    buf += decoder.decode(value, { stream: !done });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const ev = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (ev && data) yield [ev, JSON.parse(data)];
    }
    if (done) return;
  }
}

/** Like `chat`, but reports tool progress and reply text as it arrives. Resolves with the final result. */
export async function chatStream(agentId: string, sessionId: string, message: string, h: StreamHandlers = {}): Promise<ChatReply> {
  const headers = new Headers({ "content-type": "application/json" });
  const key = getApiKey();
  if (key) headers.set("authorization", `Bearer ${key}`);
  const res = await fetch(`/api/northcx/v1/agents/${agentId}/chat/stream`, { method: "POST", headers, body: JSON.stringify({ sessionId, message }) });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body?.error?.message ?? `Request failed (${res.status})`, body?.error?.reasons ?? []);
  }
  for await (const [event, data] of readEvents(res.body)) {
    const d = data as Record<string, unknown>;
    if (event === "progress" && d.type === "tool") h.onProgress?.(String(d.name));
    else if (event === "delta") h.onDelta?.(String(d.text));
    else if (event === "done") return d as unknown as ChatReply;
    else if (event === "error") throw new ApiError(500, String(d.message ?? "Run failed"));
  }
  throw new ApiError(502, "The connection closed before the reply finished");
}

export const statusLabel: Record<string, string> = {
  completed: "Completed", escalated: "Escalated", needs_approval: "Needs approval", unknown: "Unknown",
};

export function formatTime(t: number | null | undefined): string {
  return t ? new Date(t * 1000).toLocaleString() : "";
}
