export type Status = "completed" | "escalated" | "needs_approval" | "with_person" | "unknown";

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
export interface Assist { suggestedReply: string; nextSteps: string[]; keyFacts: string[]; cautions: string[]; generatedAt: number; note: string }
export interface HandoffPackage { summary: string; trigger: string; triggerDescription: string; reason: string; topics: string[]; transcript: { from: "customer" | "agent" | "platform" | "person"; text: string }[]; assist?: Assist; customerFacts: Record<string, string>; language?: string | null; actions: { tool: string; input: unknown; outcome: string; detail: unknown; traceId: string }[]; approvals: { id: string; tool: string; state: string; reason: string; input: unknown; note: string | null }[] }
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
export const resolveHandoff = (id: string, by?: string, note?: string, returnToAgent = true) =>
  api<HandoffSummary>(`/v1/handoffs/${id}/resolve`, { method: "POST", body: JSON.stringify({ ...(by ? { by } : {}), ...(note ? { note } : {}), returnToAgent }) });
export interface SimScenario { name: string; agent: string; required: boolean; description: string; steps: number; judge: boolean; digest: string; tags?: string[]; source?: "file" | "managed"; editable?: boolean }
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
export interface LiveInfo {
  spec: Record<string, unknown>; agentId: string; source: "release" | "baseline"; version: number | null; digest: string; release: ReleaseRecord | null; specYaml: string }
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
export interface ChecklistItem { key: string; title: string; status: "pass" | "fail" | "warn" | "info"; detail: string }
export interface Checklist { agent: string; version: number; environment: string; ready: boolean; checks: ChecklistItem[]; liveVersion: number | null;
  changes: { identical: boolean; instructionsChanged: boolean; toolsAdded: string[]; toolsRemoved: string[]; otherChanged: string[]; guardrailsChanged: string[] } | null }
export const getChecklist = (id: string, version: number, environment: EnvName = "production") =>
  api<Checklist>(`${agentPath(id)}/versions/${version}/checklist?environment=${environment}`);
export interface Rollout { id: string; agentId: string; environment: string; candidateVersion: number; controlVersion: number | null; percent: number; state: "active" | "promoted" | "aborted"; startedBy: string; startedAt: number; endedAt: number | null; note: string | null }
export interface ArmStats { assigned: number; conversations: number; containmentRate: Ratio; escalationRate: Ratio; guardrailBlockRate: Ratio; toolErrorRate: Ratio; satisfaction: number | null; ratings: number; tokensPerConversation: number | null; reviewed: number; judgedCorrect: Ratio }
export interface RolloutComparison { rollout: Rollout; arms: { control: ArmStats; candidate: ArmStats }; enoughData: boolean; note: string; versions: { control: number | null; candidate: number } }
export const listRollouts = (id: string) => api<{ rollouts: Rollout[] }>(`${agentPath(id)}/rollouts`).then((r) => r.rollouts);
export const startRollout = (id: string, version: number, percent: number) =>
  api<Rollout>(`${agentPath(id)}/rollouts`, { method: "POST", body: JSON.stringify({ version, percent }) });
export const setRolloutPercent = (id: string, rid: string, percent: number) =>
  api<Rollout>(`${agentPath(id)}/rollouts/${rid}/percent`, { method: "PUT", body: JSON.stringify({ percent }) });
export const promoteRollout = (id: string, rid: string) => api<Rollout>(`${agentPath(id)}/rollouts/${rid}/promote`, { method: "POST" });
export const abortRollout = (id: string, rid: string) => api<Rollout>(`${agentPath(id)}/rollouts/${rid}/abort`, { method: "POST" });
export const getRolloutComparison = (id: string, rid: string) => api<RolloutComparison>(`${agentPath(id)}/rollouts/${rid}/comparison`);
export const rollbackAgent = (id: string, by?: string, note?: string) =>
  api<ReleaseRecord>(`${agentPath(id)}/rollback`, { method: "POST", body: JSON.stringify({ ...(by ? { by } : {}), ...(note ? { note } : {}) }) });
export type EnvName = "dev" | "staging" | "production";
export interface EnvInfo { version: number | null; release: ReleaseRecord | null; servedFrom: EnvName; servedVersion: number | null }
export const getEnvironments = (id: string) => api<{ agentId: string; strictPromotion: boolean; environments: Record<EnvName, EnvInfo> }>(`${agentPath(id)}/environments`);
export const promoteAgent = (id: string, to: EnvName, by?: string, note?: string) =>
  api<ReleaseRecord>(`${agentPath(id)}/promote`, { method: "POST", body: JSON.stringify({ to, ...(by ? { by } : {}), ...(note ? { note } : {}) }) });
export const releaseToEnvironment = (id: string, version: number, environment: EnvName, by?: string, note?: string) =>
  api<ReleaseRecord>(`${agentPath(id)}/releases`, { method: "POST", body: JSON.stringify({ version, environment, ...(by ? { by } : {}), ...(note ? { note } : {}) }) });
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
export async function chatStream(agentId: string, sessionId: string, message: string, h: StreamHandlers = {}, environment?: EnvName, attachments: string[] = []): Promise<ChatReply> {
  const headers = new Headers({ "content-type": "application/json" });
  const key = getApiKey();
  if (key) headers.set("authorization", `Bearer ${key}`);
  const res = await fetch(`/api/northcx/v1/agents/${agentId}/chat/stream`, { method: "POST", headers, body: JSON.stringify({ sessionId, message, ...(environment && environment !== "production" ? { environment } : {}), ...(attachments.length ? { attachments } : {}) }) });
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

export interface Ratio { value: number | null; numerator: number; denominator: number }
export interface Overview {
  period: { from: number; to: number }; conversations: number; turns: number; environment: string; truncated: boolean; note: string;
  containmentRate: Ratio; escalationRate: Ratio; approvalRate: Ratio; guardrailBlockRate: Ratio; toolErrorRate: Ratio; errorRate: Ratio; fallbackModelRate: Ratio;
  latencySeconds: { p50: number | null; p95: number | null; samples: number };
  tokens: { total: number; perConversation: number | null; modelCalls: number };
  handoffs: { total: number; byTrigger: Record<string, number>; byQueue: Record<string, number>; byTopic: Record<string, number> };
  journeys?: Record<string, { reached: number; completed: Ratio | null; handedOff: number }>;
  languages?: { detected: Ratio; byLanguage: Record<string, { conversations: number; containmentRate: Ratio }> };
  tools: { used: Record<string, number>; errors: Record<string, number> }; guardrails: Record<string, number>;
  satisfaction: { average: number | null; responses: number; responseRate: Ratio; distribution: Record<string, number> };
  estimatedCost?: { amount: number; perConversation: number | null; basis: string };
}
export interface SeriesPoint { start: number; turns: number; conversations: number; escalated: number; guardrailBlocks: number; errors: number; tokens: number; p95Latency: number | null }
export interface FailureCause { cause: string; count: number; share: Ratio; exampleTraceIds: string[] }
export interface Gaps { unansweredSearches: { query: string; count: number }[]; messagesBeforeHandoff: { message: string; count: number }[] }
export interface AlertDelivery { status: "sent" | "retrying" | "failed" | "not_configured"; attempts: number; error?: string; at?: number }
export interface AlertEvent { event: string; rule: string; detail: string; at: number; severity: string; delivery?: AlertDelivery }
export interface AlertStatus {
  enabled: boolean; lastRun?: number | null; webhook?: boolean; undelivered?: number;
  rules?: { name: string; metric: string; threshold: number; windowMinutes: number; minSamples?: number; severity: string; cooldownMinutes?: number }[];
  active?: { rule: string; since: number; value: number; samples: number; severity: string }[]; recent?: AlertEvent[];
}
export interface Finding { id: string; rule: string; severity: string; detail: string; trace_id: string; session_id: string; agent_id: string; agent_version: number | null; created_at: number }
export const getMonitorSummary = () => api<{ rules: string[]; counts: Record<string, Record<string, number>>; total: number }>("/v1/monitor/summary");
export const getFindings = (p: { rule?: string; severity?: string } = {}) => {
  const q = new URLSearchParams({ limit: "100" });
  if (p.rule) q.set("rule", p.rule);
  if (p.severity) q.set("severity", p.severity);
  return api<{ findings: Finding[] }>(`/v1/monitor/findings?${q}`).then((r) => r.findings);
};
export const sendTestAlert = () => api<AlertEvent>("/v1/alerts/test", { method: "POST" });
const windowQuery = (hours: number, agent?: string, environment?: string) => {
  const to = Date.now() / 1000;
  const q = new URLSearchParams({ from: String(to - hours * 3600), to: String(to) });
  if (agent) q.set("agent", agent);
  if (environment && environment !== "production") q.set("environment", environment);
  return q;
};
export const getOverview = (hours: number, agent?: string, env?: string) => api<Overview>(`/v1/insights/overview?${windowQuery(hours, agent, env)}`);
export const getSeries = (hours: number, agent?: string, env?: string) => {
  const q = windowQuery(hours, agent, env);
  q.set("bucket", hours <= 48 ? "hour" : "day");
  return api<{ bucket: string; points: SeriesPoint[] }>(`/v1/insights/timeseries?${q}`);
};
export interface AskAnswer {
  answerable: boolean; answer: string; supported?: string[]; kind?: string; label?: string; value?: number | null;
  plan?: { metric: string | null; days: number; offsetDays: number; agent: string | null; compare: boolean; trend: boolean; filters?: Record<string, string | number | boolean>; find?: { q: string; status: string | null } };
  series?: { bucket: "hour" | "day"; points: { start: number; value: number | null }[] };
  rows?: { name: string; count: number }[];
  conversations?: { sessionId: string; firstMessage: string; lastStatus: string; language: string | null; handedOff: boolean; rating: number | null; endedAt: number; turns: number; lastReply: string }[];
}
export const askInsights = (question: string, environment?: string) => api<AskAnswer>("/v1/insights/ask", { method: "POST", body: JSON.stringify({ question, ...(environment ? { environment } : {}) }) });
export interface AgentDraft { specYaml: string; spec: Record<string, unknown>; warnings: string[]; notes: string[]; examples: string[]; note: string; sources: { kind: string; name: string; characters: number }[] }
export const draftAgent = (body: { agentId: string; goal: string; sources: { kind: string; name: string; text: string }[] }) =>
  api<AgentDraft>("/v1/builder/draft", { method: "POST", body: JSON.stringify(body) });
export interface ResidencyFlow { name: string; kind: string; host: string | null; data: string; region: string | null; status: "ok" | "unmapped" | "not_allowed" | "unchecked" }
export interface Residency { configured: boolean; region: string | null; allowedRegions: string[]; strict: boolean; flows: ResidencyFlow[]; compliant: boolean; problems: string[]; note: string }
export const getResidency = () => api<Residency>("/v1/residency");
export interface ScenarioDraft { scenarios: Record<string, unknown>[]; scenariosYaml: string; checked: string[]; needLiveModel: string[]; warnings: string[]; note: string }
export interface Refined { specYaml: string; spec: Record<string, unknown>; changes: string[]; warnings: string[]; notes: string[]; note: string }
export const draftScenarios = (spec: string, examples: string[]) => api<ScenarioDraft>("/v1/builder/scenarios", { method: "POST", body: JSON.stringify({ spec, examples }) });
export const refineAgent = (current: string, instruction: string) => api<Refined>("/v1/builder/refine", { method: "POST", body: JSON.stringify({ current, instruction }) });
export async function transcribeRecording(file: File): Promise<{ text: string; characters: number; note: string }> {
  const headers = new Headers({ "content-type": "application/octet-stream" });
  const key = getApiKey();
  if (key) headers.set("authorization", `Bearer ${key}`);
  const res = await fetch("/api/northcx/v1/builder/transcribe", { method: "POST", headers, body: file });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body?.error?.message ?? `Transcription failed (${res.status})`);
  return body;
}
export const getFailures = (hours: number, agent?: string, env?: string) => api<{ causes: FailureCause[] }>(`/v1/insights/failures?${windowQuery(hours, agent, env)}`).then((r) => r.causes);
export const getGaps = (hours: number, agent?: string, env?: string) => api<Gaps>(`/v1/insights/gaps?${windowQuery(hours, agent, env)}`);
export const getAlerts = () => api<AlertStatus>("/v1/alerts");
export interface ConversationRow {
  sessionId: string; agentId: string; environment: string; turns: number; startedAt: number; endedAt: number; lastStatus: string; firstMessage: string; lastReply: string;
  handedOff: boolean; handoffTriggers: string[]; rating: number | null; tags: string[]; traceIds: string[];
}
export const searchConversations = (p: { q?: string; status?: string; tag?: string; handedOff?: boolean }) => {
  const q = new URLSearchParams();
  if (p.q) q.set("q", p.q);
  if (p.status) q.set("status", p.status);
  if (p.tag) q.set("tag", p.tag);
  if (p.handedOff !== undefined) q.set("handedOff", String(p.handedOff));
  return api<{ conversations: ConversationRow[] }>(`/v1/conversations/search?${q}`).then((r) => r.conversations);
};
export const addTag = (sessionId: string, tag: string) => api<{ tags: string[] }>(`/v1/sessions/${encodeURIComponent(sessionId)}/tags/${encodeURIComponent(tag)}`, { method: "PUT" });
export const removeTag = (sessionId: string, tag: string) => api<{ tags: string[] }>(`/v1/sessions/${encodeURIComponent(sessionId)}/tags/${encodeURIComponent(tag)}`, { method: "DELETE" });

export interface CatalogTool { name: string; description: string; effect: "read" | "write"; approval: boolean; inputs: string[] }
export interface Catalog {
  tools: CatalogTool[]; guardrails: { name: string; description: string; example: Record<string, unknown> | null }[];
  inputGuardrails: { name: string }[]; outputGuardrails: { name: string }[];
  skills: { name: string; description: string; steps: string[]; tools: string[] }[]; flexibility: string[];
}
export interface SpecPreview {
  valid: boolean; problems: string[]; digest?: string; unchangedSinceLatest?: boolean;
  diffFromLive?: { identical: boolean; instructions: string | null; tools: { added: string[]; removed: string[] }; other: Record<string, unknown> } | null;
}
export const getCatalog = () => api<Catalog>("/v1/catalog");
export const previewSpec = (id: string, spec: unknown) => api<SpecPreview>(`/v1/agents/${encodeURIComponent(id)}/versions/preview`, { method: "POST", body: JSON.stringify({ spec }) });
export const saveSpec = (id: string, spec: unknown, by?: string, note?: string) =>
  api<AgentVersion>(`/v1/agents/${encodeURIComponent(id)}/versions`, { method: "POST", body: JSON.stringify({ spec, ...(by ? { by } : {}), ...(note ? { note } : {}) }) });

export interface ScenarioDetail { name: string; source: "file" | "managed"; editable: boolean; required: boolean; digest: string; definition: Record<string, any>; yaml: string; revision: number | null } // eslint-disable-line @typescript-eslint/no-explicit-any
export const getScenario = (name: string) => api<ScenarioDetail>(`/v1/simulations/scenarios/${encodeURIComponent(name)}`);
export const validateScenario = (body: { yaml?: string; scenario?: unknown }) => api<{ valid: boolean; problems: string[]; digest?: string; steps?: number }>("/v1/simulations/scenarios/validate", { method: "POST", body: JSON.stringify(body) });
export const createScenario = (body: { yaml?: string; scenario?: unknown }) => api<{ name: string; revision: number }>("/v1/simulations/scenarios", { method: "POST", body: JSON.stringify(body) });
export const updateScenario = (name: string, body: { yaml?: string; scenario?: unknown }) => api<{ name: string; revision: number }>(`/v1/simulations/scenarios/${encodeURIComponent(name)}`, { method: "PUT", body: JSON.stringify(body) });
export const deleteScenario = (name: string) => api<{ deleted: boolean }>(`/v1/simulations/scenarios/${encodeURIComponent(name)}`, { method: "DELETE" });
export const getScenarioDraft = (sessionId: string) => api<{ yaml: string; scenario: Record<string, unknown>; warnings: string[] }>(`/v1/sessions/${encodeURIComponent(sessionId)}/scenario-draft`);

export interface KnowledgeSource { id: string; name: string; staleAfterDays: number | null; createdAt: number }
export interface KnowledgeDoc { id: string; sourceId: string; externalId: string; title: string; url: string | null; chunks: number; sourceUpdatedAt: number | null; ingestedAt: number; stale: boolean }
export interface Passage { documentId: string; sourceId: string; title: string; url: string | null; section: string; text: string; score: number; updatedAt: number; stale: boolean; via?: "keyword" | "meaning" | "both" }
export interface IndexStatus { enabled: boolean; model?: string; indexed?: number; passages?: number; pending?: number; lastRun?: number | null; lastError?: string | null }
export const getIndexStatus = () => api<IndexStatus>("/v1/knowledge/index");
export const rebuildIndex = () => api<{ cleared: number }>("/v1/knowledge/index/rebuild", { method: "POST" });
export const listKnowledgeSources = () => api<{ sources: KnowledgeSource[] }>("/v1/knowledge/sources").then((r) => r.sources);
export const createKnowledgeSource = (id: string, name: string, staleAfterDays?: number) =>
  api<KnowledgeSource>("/v1/knowledge/sources", { method: "POST", body: JSON.stringify({ id, name, ...(staleAfterDays ? { staleAfterDays } : {}) }) });
export const deleteKnowledgeSource = (id: string) => api<{ deleted: boolean; documents: number }>(`/v1/knowledge/sources/${encodeURIComponent(id)}`, { method: "DELETE" });
export const listKnowledgeDocs = (source?: string, staleOnly?: boolean) => {
  const q = new URLSearchParams();
  if (source) q.set("source", source);
  if (staleOnly) q.set("stale", "true");
  return api<{ documents: KnowledgeDoc[] }>(`/v1/knowledge/documents${q.size ? `?${q}` : ""}`).then((r) => r.documents);
};
const docPath = (source: string, ext: string) => `/v1/knowledge/sources/${encodeURIComponent(source)}/documents/${ext.split("/").map(encodeURIComponent).join("/")}`;
export const getKnowledgeDoc = (source: string, ext: string) => api<KnowledgeDoc & { text: string; textRebuilt: boolean }>(docPath(source, ext));
export const putKnowledgeDoc = (source: string, ext: string, body: { title: string; text: string; url?: string; sourceUpdatedAt?: number }) =>
  api<{ status: string; document: KnowledgeDoc }>(docPath(source, ext), { method: "PUT", body: JSON.stringify(body) });
export const deleteKnowledgeDoc = (source: string, ext: string) => api<{ deleted: boolean }>(docPath(source, ext), { method: "DELETE" });
export const searchKnowledge = (q: string, source?: string) =>
  api<{ passages: Passage[] }>(`/v1/knowledge/search?${new URLSearchParams({ q, ...(source ? { source } : {}) })}`).then((r) => r.passages);

export const statusLabel: Record<string, string> = {
  completed: "Completed", escalated: "Escalated", needs_approval: "Needs approval", unknown: "Unknown",
};

export function formatTime(t: number | null | undefined): string {
  return t ? new Date(t * 1000).toLocaleString() : "";
}

export const FAILURE_KINDS = ["wrong_answer", "missed_policy", "hallucination", "bad_tone", "tool_misuse", "unneeded_handoff", "missed_handoff", "slow", "other"] as const;
export interface ReviewRecord { verdict: "correct" | "wrong"; handoff: string; failures: string[]; note: string; reviewer: string; reviewedAt: number }
export interface QueueRow { sessionId: string; agentId: string; turns: number; startedAt: number; endedAt: number; lastStatus: string; firstMessage: string; reasons: string[]; weight: number; handedOff: boolean; rating: number | null; review: ReviewRecord | null }
export interface ReviewContext { sessionId: string; transcript: { from: string; text: string }[]; tags: string[]; traces: { id: string; status: string; tools: string[]; startedAt: number | null; agentVersion?: string }[]; handoffs: { id: string; trigger: string; state: string; queue: string | null; reason: string }[]; rating: number | null; review: ReviewRecord | null }
export interface ReviewQuality { reviewed: number; correctRate: Ratio; escalationCorrectness: Ratio; unneededEscalationRate: Ratio; failuresByKind: Record<string, number>; note: string }
export const getReviewQueue = (includeReviewed: boolean) => api<{ queue: QueueRow[] }>(`/v1/reviews/queue?includeReviewed=${includeReviewed}`).then((r) => r.queue);
export const getReviewContext = (id: string) => api<ReviewContext>(`/v1/sessions/${encodeURIComponent(id)}/transcript`);
export const saveReview = (id: string, body: { verdict: string; handoff: string; failures: string[]; note: string }) =>
  api<{ saved: boolean; replaced: boolean }>(`/v1/sessions/${encodeURIComponent(id)}/review`, { method: "PUT", body: JSON.stringify(body) });
export const getReviewQuality = () => api<ReviewQuality>("/v1/insights/review-quality");

export const getSsoConfig = () =>
  fetch("/api/northcx/auth/sso/config").then((r) => (r.ok ? (r.json() as Promise<{ enabled: boolean; loginUrl: string | null }>) : { enabled: false, loginUrl: null })).catch(() => ({ enabled: false, loginUrl: null }));
export const signOut = () => api<{ revoked: boolean }>("/v1/me/logout", { method: "POST" });

export interface Journey { name: string; goal: string; when?: string; steps: { purpose: string; tool?: string | null; required?: boolean }[]; rules?: string[]; done_when?: string[]; handoff_if?: string[]; flexibility?: string; samples?: string[] }
export const draftJourney = (agent: string, description: string) =>
  api<{ journey: Journey; yaml: string; warnings: string[]; note: string }>(`/v1/agents/${encodeURIComponent(agent)}/journeys/draft`, { method: "POST", body: JSON.stringify({ description }) });
export const journeyScenarios = (agent: string, journey: Journey) =>
  api<{ scenarios: Record<string, unknown>[]; yaml: string }>(`/v1/agents/${encodeURIComponent(agent)}/journeys/scenarios`, { method: "POST", body: JSON.stringify({ journey }) });

export const replyToCustomer = (id: string, text: string) => api<{ sent: boolean }>(`/v1/handoffs/${id}/reply`, { method: "POST", body: JSON.stringify({ text }) });
export const suggestHelp = (id: string) => api<{ assist: Assist }>(`/v1/handoffs/${id}/assist`, { method: "POST" }).then((r) => r.assist);

export interface AttachmentInfo { id: string; name: string; kind: "image" | "pdf" | "text"; mediaType: string; size: number; sha256: string; createdAt: number }
export async function uploadAttachment(sessionId: string, file: File): Promise<AttachmentInfo> {
  const headers = new Headers({ "content-type": "application/octet-stream" });
  const key = getApiKey();
  if (key) headers.set("authorization", `Bearer ${key}`);
  const res = await fetch(`/api/northcx/v1/sessions/${encodeURIComponent(sessionId)}/attachments?filename=${encodeURIComponent(file.name)}`, { method: "PUT", headers, body: file });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body?.error?.message ?? `Upload failed (${res.status})`);
  return body as AttachmentInfo;
}
/** Fetches the file with the session key and opens it as a download (a plain link could not send the key). */
export async function downloadAttachment(a: { id: string; name: string }): Promise<void> {
  const headers = new Headers();
  const key = getApiKey();
  if (key) headers.set("authorization", `Bearer ${key}`);
  const res = await fetch(`/api/northcx/v1/attachments/${a.id}`, { headers });
  if (!res.ok) throw new ApiError(res.status, "Could not download the file");
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url; link.download = a.name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export interface CrawlJob { jobId: string; sourceId: string; host: string; state: "running" | "done" | "failed" | "stopped"; startedAt: number; finishedAt: number | null; fetched: number; created: number; updated: number; unchanged: number; skipped: Record<string, number>; pruned: number; errors: string[]; message: string }
export const listCrawls = () => api<{ enabled: boolean; crawls: CrawlJob[] }>("/v1/knowledge/crawls");
export interface CrawlSchedule { id: string; sourceId: string; url: string; maxPages: number; maxDepth: number; prune: boolean; everyHours: number; nextRun: number; lastRun: number | null; lastResult: string | null; enabled: boolean }
export const listSchedules = () => api<{ enabled: boolean; schedules: CrawlSchedule[] }>("/v1/knowledge/schedules");
export const createSchedule = (source: string, body: { url: string; maxPages: number; maxDepth: number; includePaths: string[]; excludePaths: string[]; prune: boolean; everyHours: number }) =>
  api<CrawlSchedule>(`/v1/knowledge/sources/${encodeURIComponent(source)}/schedule`, { method: "POST", body: JSON.stringify(body) });
export const deleteSchedule = (id: string) => api<{ deleted: boolean }>(`/v1/knowledge/schedules/${encodeURIComponent(id)}`, { method: "DELETE" });
export const setScheduleEnabled = (id: string, enabled: boolean) => api<{ enabled: boolean }>(`/v1/knowledge/schedules/${encodeURIComponent(id)}/enabled`, { method: "POST", body: JSON.stringify({ enabled }) });
export const startCrawl = (source: string, body: { url: string; maxPages: number; maxDepth: number; includePaths: string[]; excludePaths: string[]; prune: boolean }) =>
  api<CrawlJob>(`/v1/knowledge/sources/${encodeURIComponent(source)}/crawl`, { method: "POST", body: JSON.stringify(body) });
export async function importKnowledgeFile(source: string, file: File): Promise<{ status: string; kind: string; document: KnowledgeDoc }> {
  const headers = new Headers({ "content-type": "application/octet-stream" });
  const key = getApiKey();
  if (key) headers.set("authorization", `Bearer ${key}`);
  const res = await fetch(`/api/northcx/v1/knowledge/sources/${encodeURIComponent(source)}/import?filename=${encodeURIComponent(file.name)}`, { method: "POST", headers, body: file });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body?.error?.message ?? `Import failed (${res.status})`);
  return body;
}
