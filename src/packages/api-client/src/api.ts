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
  containmentRate: Ratio; resolutionRate: Ratio & { pending: number; windowDays: number; provisional: boolean }; escalationRate: Ratio; approvalRate: Ratio; guardrailBlockRate: Ratio; toolErrorRate: Ratio; errorRate: Ratio; fallbackModelRate: Ratio;
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

export interface CatalogTool { name: string; description: string; effect: "read" | "write"; source?: string; approval: boolean; inputs: string[] }
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

// ---- agent hub (templates) ----
export interface TemplateInfo { id: string; title: string; description: string; intent: string; parameters: { name: string; description: string; default: string | null; required: boolean }[]; requiresTools: string[]; scenarios: number; audience?: string; category?: string; channels?: string[]; version?: string; notes?: string; sees?: string[]; does?: string[]; needs?: { tools: string[]; knowledge: boolean; channels: string[] }; provenance?: TemplateProvenance }
export interface TemplateProvenance { source: "built-in" | "organization" | "file"; signed: boolean; verified: boolean; status: string; keyFingerprint?: string | null; proposedBy?: string | null; approvedBy?: string | null }
export interface TemplateRender { specYaml: string; scenariosYaml: string; scenarios: number; missingTools: string[]; warnings: string[] }
export const listTemplates = () => api<{ templates: TemplateInfo[] }>("/v1/templates").then((r) => r.templates);
export const renderTemplate = (id: string, agentId: string, params: Record<string, string>) =>
  api<TemplateRender>(`/v1/templates/${id}/render`, { method: "POST", body: JSON.stringify({ agentId, params }) });
export interface TemplateInstall extends TemplateRender { agentId: string; number: number; scenariosSaved: string[]; scenariosSkipped: string[] }
/** Saves the rendered agent as a draft version (never live) and, when asked, the template's test scenarios. */
export const createFromTemplate = (id: string, agentId: string, params: Record<string, string>, saveScenarios = true) =>
  api<TemplateInstall>(`/v1/templates/${id}/create-version`, { method: "POST", body: JSON.stringify({ agentId, params, saveScenarios }) });

// ---------- Workspace (staff Pilot, tasks, search, memory) ----------
export interface PilotSource { title: string | null; url: string | null; section: string | null; updated: string | null; stale: boolean }
export interface PilotAction { id: string; tool: string; summary: string; state: string; result: string; expiresAt: number }
export interface PilotReply { actions?: PilotAction[]; chatId: string; reply: string; status: Status; traceId: string | null; sources: PilotSource[]; tools: string[]; temporary: boolean; memory: boolean }
export const pilotChat = (message: string, opts: { chatId?: string; style?: "quick" | "research" | "think" | "do"; memory?: boolean; temporary?: boolean; spaceId?: string } = {}) =>
  api<PilotReply>("/v1/workspace/chat", { method: "POST", body: JSON.stringify({ message, ...opts }) });

export type TaskStatus = "draft" | "needs_answers" | "planned" | "approved" | "running" | "paused" | "done" | "stopped" | "failed";
export interface PilotTaskStep { n: number; text: string; status: string; startedAt: number; endedAt: number | null; tokens: number; tools: string[]; sources: { title: string | null; section: string | null; stale: boolean }[]; error?: string }
export interface PilotTask {
  id: string; style: string; prompt: string; status: TaskStatus; questions: { q: string; chips: string[] }[]; answers: string[];
  plan: { n: number; text: string; source: string }[]; steps: PilotTaskStep[]; results: { v: number; text: string; sources: { title: string | null; section: string | null; stale: boolean }[]; createdAt: number; tokens: number }[];
  tokens: number; note: string; createdAt: number; updatedAt: number; limits: { steps: number; tokens: number };
}
export const createTask = (prompt: string) => api<PilotTask>("/v1/workspace/tasks", { method: "POST", body: JSON.stringify({ prompt, style: "research" }) });
export const listTasks = () => api<{ tasks: PilotTask[] }>("/v1/workspace/tasks").then((r) => r.tasks);
export const getTask = (id: string) => api<PilotTask>(`/v1/workspace/tasks/${id}`);
export const answerTask = (id: string, answers: string[]) => api<PilotTask>(`/v1/workspace/tasks/${id}/answers`, { method: "POST", body: JSON.stringify({ answers }) });
export const editTaskPlan = (id: string, steps: { text: string; source?: string }[]) => api<PilotTask>(`/v1/workspace/tasks/${id}/plan`, { method: "PUT", body: JSON.stringify({ steps }) });
export const approveTask = (id: string) => api<PilotTask>(`/v1/workspace/tasks/${id}/approve`, { method: "POST" });
export const controlTask = (id: string, action: "pause" | "stop") => api<PilotTask>(`/v1/workspace/tasks/${id}/${action}`, { method: "POST" });
export const deleteTask = (id: string) => api<{ deleted: boolean }>(`/v1/workspace/tasks/${id}`, { method: "DELETE" });

export interface WorkspaceResult { kind: "knowledge" | "conversation" | "handoff"; id: string; title: string; snippet: string; why: string; provider: string; url: string | null; meta: Record<string, unknown>; score: number }
export const workspaceSearch = (q: string) => api<{ results: WorkspaceResult[]; skipped: { source: string; reason: string }[]; searched: string[] }>(`/v1/workspace/search?q=${encodeURIComponent(q)}`);

export interface MemoryNote { id: string; note: string; createdAt: number; updatedAt: number }
export const listNotes = () => api<{ notes: MemoryNote[] }>("/v1/workspace/memory").then((r) => r.notes);
export const addNote = (note: string) => api<{ id: string; note: string; new: boolean }>("/v1/workspace/memory", { method: "POST", body: JSON.stringify({ note }) });
export const deleteNote = (id: string) => api<{ deleted: boolean }>(`/v1/workspace/memory/${id}`, { method: "DELETE" });
export const eraseNotes = () => api<{ removed: number }>("/v1/workspace/memory", { method: "DELETE" });


// ---------- Agent Hub ----------
export interface HubCheck { id: string; label: string; ok: boolean; blocking: boolean; detail: string }
export interface HubRequirements { ok: boolean; checks: HubCheck[] }
export interface HubInstall { agent: string; template: string; templateVersion: string; params: Record<string, string>; version: number; installedBy: string; scenarios: string[]; tests: { ran?: boolean; passed?: boolean; counts?: { total: number; passed: number; failed: number }; reason?: string }; installedAt: number; updatedAt: number; title: string; currentTemplateVersion: string | null; updateAvailable: boolean; templateAvailable: boolean }
export interface HubUpdatePreview { from: string; to: string; installedVersion: number; currentVersion: number | null; templateChanges: { identical: boolean; instructions: string | null; tools: { added: string[]; removed: string[] }; other: Record<string, unknown> }; localChanges: { identical: boolean; instructions: string | null; tools: { added: string[]; removed: string[] }; other: Record<string, unknown> }; scenarios: { added: string[]; removed: string[]; kept: string[] } }
export const hubRequirements = (id: string, agentId: string, params: Record<string, string>) => api<HubRequirements>(`/v1/templates/${id}/requirements`, { method: "POST", body: JSON.stringify({ agentId, params }) });
export const hubInstall = (id: string, agentId: string, params: Record<string, string>) =>
  api<{ agent: string; version: number; live: boolean; requirements: HubRequirements; scenariosSaved: string[]; tests: HubInstall["tests"] }>(`/v1/templates/${id}/install`, { method: "POST", body: JSON.stringify({ agentId, params }) });
export const hubInstalls = () => api<{ installs: HubInstall[] }>("/v1/hub/installs").then((r) => r.installs);
export const hubUpdatePreview = (id: string, agentId: string) => api<HubUpdatePreview>(`/v1/templates/${id}/update-preview`, { method: "POST", body: JSON.stringify({ agentId }) });
export const hubUpdate = (id: string, agentId: string) => api<{ version: number; live: boolean; scenariosSaved: string[] }>(`/v1/templates/${id}/update`, { method: "POST", body: JSON.stringify({ agentId }) });

// ---------- Models and budgets, Usage, Policies, Groups ----------
export interface ModelsOverview {
  configured: boolean; note: string; fallbacks?: string[];
  providers: { name: string; defaultModel: string | null; isDefault: boolean; tier: string; capabilities: { tools: boolean; parallelTools: boolean; images: boolean; documents: boolean; maxContextTokens: number | null }; prices: Record<string, { inputPerMillion: number; outputPerMillion: number; currency: string }> }[];
  routing?: { policy: { sensitive: string[]; normal: string[]; publicCloudAllowedAgents: string[] }; sensitiveTopics: string[]; rules: { name: string; when: Record<string, unknown>; use: { tier?: string; model?: string } }[]; qualification: { required: boolean; exempt: string[] } } | null;
  budget: { dailyTokenLimit: number | null; dailyMoneyLimit: number | null; currency: string; setHere?: { dailyTokenLimit?: number; dailyMoneyLimit?: number; currency?: string }; tokensToday: number; moneyToday: number };
}
export const modelsOverview = () => api<ModelsOverview>("/v1/models/overview");
export interface UsageDim { name: string; tokens: number; cost: number }
export interface UsageReport { days: number; currency: string; byModel: UsageDim[]; byTeam: UsageDim[]; rows: { agent: string; day: string; tokens: number; cost: number }[]; byAgent: { agent: string; tokens: number; cost: number }[]; totals: { tokens: number; cost: number }; limits: { dailyTokenLimit: number | null; dailyMoneyLimit: number | null } }
export const usageReport = (days: number) => api<UsageReport>(`/v1/usage?days=${days}`);
export interface PolicyInfo { name: string; description: string; exampleConfig: Record<string, unknown>; cases: { on: string; input: unknown; expected: "allowed" | "blocked" }[] }
export const policyLibrary = () => api<{ policies: PolicyInfo[]; note: string }>("/v1/policies");
export interface GroupInfo { id: string; name: string; roles: string[]; members: string[]; externalName: string | null; description: string; createdBy: string; createdAt: number }
export const listGroups = () => api<{ groups: GroupInfo[] }>("/v1/groups").then((r) => r.groups);
export const createGroup = (name: string, roles: string[], externalName?: string) => api<GroupInfo>("/v1/groups", { method: "POST", body: JSON.stringify({ name, roles, ...(externalName ? { externalName } : {}) }) });
export const updateGroup = (id: string, patch: { roles?: string[]; externalName?: string; description?: string }) => api<GroupInfo>(`/v1/groups/${id}`, { method: "PUT", body: JSON.stringify(patch) });
export const deleteGroup = (id: string) => api<{ deleted: boolean }>(`/v1/groups/${id}`, { method: "DELETE" });
export const addGroupMember = (id: string, subject: string) => api<GroupInfo>(`/v1/groups/${id}/members`, { method: "POST", body: JSON.stringify({ subject }) });
export const removeGroupMember = (id: string, subject: string) => api<GroupInfo>(`/v1/groups/${id}/members/${encodeURIComponent(subject)}`, { method: "DELETE" });
export const setBudgets = (b: { dailyTokenLimit?: number | null; dailyMoneyLimit?: number | null; currency?: string }) => api<{ saved: boolean }>("/v1/budgets", { method: "PUT", body: JSON.stringify(b) });
export const clearBudgets = () => api<{ cleared: boolean }>("/v1/budgets", { method: "DELETE" });

// ---------- Organization policies (E16) ----------
export interface OrgPolicyCase { on: string; input: unknown; expected: "allowed" | "blocked" }
export interface OrgPolicyProof { passed: boolean; problems: string[]; results: { ok: boolean; got?: string; expected?: string; note?: string }[] }
export interface OrgPolicy {
  id: string; version: number; status: "draft" | "proposed" | "active" | "rejected" | "superseded" | "retired"; locked: boolean;
  name: string; policy: string; config: Record<string, unknown>; cases: OrgPolicyCase[]; appliesTo: string[] | null; proof: OrgPolicyProof;
  createdBy: string; proposedBy: string | null; decidedBy: string | null; decisionNote: string | null;
  versions?: { version: number; status: string; createdBy: string; decidedBy: string | null }[];
}
export const orgPolicies = () => api<{ policies: OrgPolicy[] }>("/v1/org-policies").then((r) => r.policies);
export const proveOrgPolicy = (policy: string, config: Record<string, unknown>, cases: OrgPolicyCase[]) => api<OrgPolicyProof>("/v1/org-policies/prove", { method: "POST", body: JSON.stringify({ policy, config, cases }) });
export const createOrgPolicy = (b: { name: string; policy: string; config: Record<string, unknown>; cases: OrgPolicyCase[]; appliesTo?: string[] }) => api<OrgPolicy>("/v1/org-policies", { method: "POST", body: JSON.stringify(b) });
export const editOrgPolicy = (id: string, b: { config?: Record<string, unknown>; cases?: OrgPolicyCase[]; appliesTo?: string[] }) => api<OrgPolicy>(`/v1/org-policies/${id}`, { method: "PUT", body: JSON.stringify(b) });
export const proposeOrgPolicy = (id: string) => api<OrgPolicy>(`/v1/org-policies/${id}/propose`, { method: "POST" });
export const decideOrgPolicy = (id: string, action: "approve" | "reject" | "retire", note?: string) => api<OrgPolicy>(`/v1/org-policies/${id}/${action}`, { method: "POST", body: JSON.stringify({ note }) });

// ---------- Organization templates (WP22.5) ----------
export interface OrgTemplate { id: string; version: number; title: string; status: "draft" | "proposed" | "published" | "rejected" | "superseded" | "withdrawn"; audience: string; scenarios: number;
  check: { ok: boolean; problems: string[]; scenarios?: number }; createdBy: string; proposedBy: string | null; decidedBy: string | null; decisionNote: string | null; data?: Record<string, unknown>; yaml?: string;
  versions?: { version: number; status: string; createdBy: string; decidedBy: string | null }[] }
export const orgTemplates = () => api<{ templates: OrgTemplate[] }>("/v1/org-templates").then((r) => r.templates);
export const orgTemplate = (id: string) => api<OrgTemplate>(`/v1/org-templates/${id}`);
export const checkOrgTemplate = (yaml: string) => api<{ ok: boolean; problems: string[]; scenarios: number; id: string; title: string }>("/v1/org-templates/check", { method: "POST", body: JSON.stringify({ yaml }) });
export const createOrgTemplate = (yaml: string) => api<OrgTemplate>("/v1/org-templates", { method: "POST", body: JSON.stringify({ yaml }) });
export const reviseOrgTemplate = (id: string, yaml: string) => api<OrgTemplate>(`/v1/org-templates/${id}`, { method: "PUT", body: JSON.stringify({ yaml }) });
export const proposeOrgTemplate = (id: string) => api<OrgTemplate>(`/v1/org-templates/${id}/propose`, { method: "POST" });
export const decideOrgTemplate = (id: string, action: "approve" | "reject" | "withdraw", note?: string) => api<OrgTemplate>(`/v1/org-templates/${id}/${action}`, { method: "POST", body: JSON.stringify({ note }) });

// ---------- Staff assistants (the Workspace catalog) ----------
export interface StaffAssistant { id: string; version: number | null; description: string; tools: { name: string; description: string }[]; unavailableTools: string[] }
export const staffAssistants = () => api<{ assistants: StaffAssistant[] }>("/v1/workspace/assistants").then((r) => r.assistants);
export const assistantChat = (id: string, message: string, opts: { chatId?: string; memory?: boolean; temporary?: boolean } = {}) =>
  api<{ chatId: string; assistant: string; reply: string; status: string; traceId: string | null; sources: PilotSource[]; tools: string[]; temporary: boolean }>(`/v1/workspace/assistants/${id}/chat`, { method: "POST", body: JSON.stringify({ message, ...opts }) });

// ---------- Performance (Workspace) ----------
export interface TimeStats { count: number; medianSeconds: number | null; p90Seconds: number | null }
export interface PerfSeries { day: string; count: number }
export interface PerformanceReport {
  days: number; individualsShown: boolean; counts: Record<string, string>;
  mine: { handoffsResolved: number; approvalsDecided: number; approved: number; rejected: number; handoffTime: TimeStats; approvalTime: TimeStats; series: PerfSeries[] };
  team: { handoffsResolved: number; approvalsDecided: number; handlers: number; handoffTime: TimeStats; approvalTime: TimeStats; openNow: number; oldestOpenSeconds: number | null; afterHours: number; series: PerfSeries[]; people?: { name: string; items: number }[]; byTeam?: { team: string; handoffsResolved: number; approvalsDecided: number; handoffTime: TimeStats; approvalTime: TimeStats }[] };
}
export const performance = (days: number, individuals = false) => api<PerformanceReport>(`/v1/workspace/performance?days=${days}${individuals ? "&individuals=true" : ""}`);

// ---------- Quality (Workspace) ----------
export interface RubricCriterion { id: string; label: string; weight: number; check: string; n?: number; phrases?: string[] }
export interface Rubric { criteria: RubricCriterion[]; passMark: number; sample: number; version: number; isDefault: boolean; checks?: { kinds: string[] } }
export interface QaScored { sessionId: string; agentId: string; turns: number; score: number | null; criteria: { id: string; label: string; weight: number; result: "pass" | "fail" | "na"; reason: string | null }[] }
export interface Scorecards {
  days: number; rubricVersion: number; passMark: number; scored: number; conversations: number; averageScore: number | null; passRate: { value: number | null; numerator: number; denominator: number };
  byAgent: { agent: string; scored: number; average: number }[]; byCheck: { id: string; label: string; passed: number; failed: number }[]; lowest: QaScored[]; sampleToReview: string[]; truncated: boolean; note: string;
}
export interface Calibration { model?: { judged: number; compared: number; agreement: { value: number | null; numerator: number; denominator: number }; disagreements: { sessionId: string; score: number; verdict: string }[]; note: string }; compared: number; agreement: { value: number | null; numerator: number; denominator: number }; scoreSaidGoodReviewerSaidWrong: number; scoreSaidBadReviewerSaidCorrect: number; disagreements: { sessionId: string; score: number; verdict: string }[]; note: string; passMark: number }
export interface CoachingNote { id: string; sessionId: string; about: string; note: string; author: string; createdAt: number }
export const getRubric = () => api<Rubric>("/v1/quality/rubric");
export const putRubric = (r: { criteria: RubricCriterion[]; passMark: number; sample: number }) => api<Rubric>("/v1/quality/rubric", { method: "PUT", body: JSON.stringify(r) });
export const resetRubric = () => api<{ reset: boolean }>("/v1/quality/rubric", { method: "DELETE" });
export const scorecards = (days: number) => api<Scorecards>(`/v1/quality/scorecards?days=${days}`);
export const qaCalibration = (days: number) => api<Calibration>(`/v1/quality/calibration?days=${days}`);
export const coachingNotes = (sessionId?: string) => api<{ notes: CoachingNote[] }>(`/v1/quality/coaching${sessionId ? `?sessionId=${encodeURIComponent(sessionId)}` : ""}`).then((r) => r.notes);
export const addCoachingNote = (sessionId: string, about: string, note: string) => api<CoachingNote>("/v1/quality/coaching", { method: "POST", body: JSON.stringify({ sessionId, about, note }) });
export const deleteCoachingNote = (id: string) => api<{ deleted: boolean }>(`/v1/quality/coaching/${id}`, { method: "DELETE" });

// ---------- Customers (Workspace) ----------
export interface CustomerNoteItem { id: string; note: string; author: string; createdAt: number }
export interface CustomerRecord {
  ref: string; id: string; idMasked: boolean; sessions: number; windowDays: number; truncated: boolean; note: string;
  timeline: { sessionId: string; agentId: string; channel: string | null; startedAt: number; endedAt: number; turns: number; lastStatus: string; firstMessage: string; handedOff: boolean; handoffReasons: string[]; rating: number | null; review: string | null }[];
  satisfaction: { rated: number; average: number | null; handedOff: number; counts: string };
  facts: { id: string; text: string; sourceSession: string | null; createdAt: number; addedBy: string }[];
  notes: CustomerNoteItem[];
}
export type CustomerTarget = string | { sessionId: string };      // the identifier, or the customer of a conversation found without it
const target = (t: CustomerTarget) => (typeof t === "string" ? { customerId: t } : t);
export interface OrderMatch { sessionId: string; customerRef: string | null; agentId: string; startedAt: number; firstMessage: string }
export const customerFind = (orderNumber: string) => api<{ matches: OrderMatch[]; note: string; truncated: boolean }>("/v1/customers/find", { method: "POST", body: JSON.stringify({ orderNumber }) });
export const customerLookup = (t: CustomerTarget) => api<CustomerRecord>("/v1/customers/lookup", { method: "POST", body: JSON.stringify(target(t)) });
export const customerReveal = (t: CustomerTarget, reason: string) => api<{ ref: string; id: string }>("/v1/customers/reveal", { method: "POST", body: JSON.stringify({ ...target(t), reason }) });
export const customerAddNote = (t: CustomerTarget, note: string) => api<CustomerNoteItem>("/v1/customers/notes", { method: "POST", body: JSON.stringify({ ...target(t), note }) });
export const customerDeleteNote = (t: CustomerTarget, noteId: string) => api<{ deleted: boolean }>(`/v1/customers/notes/${noteId}/delete`, { method: "POST", body: JSON.stringify(target(t)) });
export const customerRemoveFact = (t: CustomerTarget, factId: string, reason: string) => api<{ removed: boolean }>(`/v1/customers/facts/${factId}/remove`, { method: "POST", body: JSON.stringify({ ...target(t), reason }) });
export const customersEnabled = () => api<{ enabled: boolean }>("/v1/customers/settings");
export const setCustomersEnabled = (enabled: boolean) => api<{ enabled: boolean }>("/v1/customers/settings", { method: "PUT", body: JSON.stringify({ enabled }) });

// ---------- Automations (Workspace) ----------
export interface AutoRun { waiting?: { step: number; ask: string; preview: string; until: number } | null; id: string; automationId: string; version: number; trigger: string; by: string; status: "running" | "waiting" | "rejected" | "succeeded" | "failed" | "stopped" | "timed_out"; startedAt: number; endedAt: number | null;
  steps: { id: string; kind: string; status: string; output?: string; error?: string; traceId?: string }[]; outcome: string; error: string | null }
export interface Automation { id: string; version: number; name: string; status: "draft" | "proposed" | "published" | "rejected" | "superseded" | "retired"; trigger: { type: string; everyHours?: number }; steps: number;
  createdBy: string; proposedBy: string | null; decidedBy: string | null; paused: boolean; nextRun: number | null; lastRun: AutoRun | null; yaml?: string; versions?: { version: number; status: string }[] }
export const automations = () => api<{ enabled: boolean; automations: Automation[] }>("/v1/automations");
export const automation = (id: string) => api<Automation>(`/v1/automations/${id}`);
const body = (x: string | object) => JSON.stringify(typeof x === "string" ? { yaml: x } : { definition: x });
export const createAutomation = (x: string | object) => api<Automation & { webhookSecret?: string }>("/v1/automations", { method: "POST", body: body(x) });
export const reviseAutomation = (id: string, x: string | object) => api<Automation>(`/v1/automations/${id}`, { method: "PUT", body: body(x) });
export const automationAction = (id: string, action: "propose" | "approve" | "reject" | "retire" | "pause" | "resume" | "run", body: object = {}) => api<unknown>(`/v1/automations/${id}/${action}`, { method: "POST", body: JSON.stringify(body) });
export const automationRuns = (id: string) => api<{ runs: AutoRun[] }>(`/v1/automations/${id}/runs`).then((r) => r.runs);
export const setAutomationsEnabled = (enabled: boolean) => api<{ enabled: boolean }>("/v1/automation-settings", { method: "PUT", body: JSON.stringify({ enabled }) });

// ---------- Outputs and Spaces (Workspace) ----------
export interface OutputItem { id: string; title: string; kind: string; visibility: "private" | "team" | "shared"; team?: string | null; owner: string; spaceId: string | null; source: string; version: number; versions: number; createdAt: number; updatedAt: number; expiresAt: number; size: number; body?: string; history?: { n: number; at: number; by: string; size: number }[] }
export interface SpaceItem { id: string; name: string; description: string; instructions: string; visibility: "private" | "team" | "shared"; team?: string | null; owner: string; updatedAt: number; outputs?: OutputItem[] }
export const listOutputs = (opts: { space?: string; kind?: string; mine?: boolean } = {}) =>
  api<{ outputs: OutputItem[] }>(`/v1/workspace/outputs?${new URLSearchParams({ ...(opts.space ? { space: opts.space } : {}), ...(opts.kind ? { kind: opts.kind } : {}), ...(opts.mine ? { mine: "true" } : {}) })}`).then((r) => r.outputs);
export const getOutput = (id: string) => api<OutputItem>(`/v1/workspace/outputs/${id}`);
export const saveOutput = (b: { title: string; body: string; kind?: string; visibility?: string; spaceId?: string; source?: "manual" | "pilot" }) => api<OutputItem>("/v1/workspace/outputs", { method: "POST", body: JSON.stringify(b) });
export const editOutput = (id: string, b: { title?: string; body?: string; visibility?: string }) => api<OutputItem>(`/v1/workspace/outputs/${id}`, { method: "PUT", body: JSON.stringify(b) });
export const deleteOutput = (id: string) => api<{ deleted: boolean }>(`/v1/workspace/outputs/${id}`, { method: "DELETE" });
export async function downloadOutput(id: string, format: string, name: string): Promise<void> {
  const key = getApiKey();
  const res = await fetch(`/api/northcx/v1/workspace/outputs/${id}/export?format=${format}`, { headers: key ? { authorization: `Bearer ${key}` } : {} });
  if (!res.ok) throw new Error(((await res.json().catch(() => null)) as { error?: { message?: string } } | null)?.error?.message ?? `Download failed (${res.status})`);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url; a.download = `${name.replace(/[^A-Za-z0-9_-]+/g, "-").slice(0, 60) || "output"}.${format}`;
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}
export const listSpaces = () => api<{ spaces: SpaceItem[] }>("/v1/workspace/spaces").then((r) => r.spaces);
export const getSpace = (id: string) => api<SpaceItem>(`/v1/workspace/spaces/${id}`);
export const createSpace = (b: { name: string; description?: string; instructions?: string; visibility?: string }) => api<SpaceItem>("/v1/workspace/spaces", { method: "POST", body: JSON.stringify(b) });
export const editSpace = (id: string, b: Partial<{ name: string; description: string; instructions: string; visibility: string }>) => api<SpaceItem>(`/v1/workspace/spaces/${id}`, { method: "PUT", body: JSON.stringify(b) });
export const deleteSpace = (id: string) => api<{ deleted: boolean }>(`/v1/workspace/spaces/${id}`, { method: "DELETE" });
export const judgeConversation = (sessionId: string) => api<{ sessionId: string; verdict: "good" | "poor"; reason: string; by: string }>("/v1/quality/judge", { method: "POST", body: JSON.stringify({ sessionId }) });
export const waitingRuns = () => api<{ runs: AutoRun[] }>("/v1/automation-runs?status=waiting").then((r) => r.runs);
export const decideRun = (id: string, approve: boolean, note?: string) => api<AutoRun>(`/v1/automation-runs/${id}/decision`, { method: "POST", body: JSON.stringify({ approve, note }) });
export interface AutomationCatalog { reports: string[]; events: string[]; destinations: string[]; assistants: string[]; kinds: string[]; triggers: string[] }
export const automationCatalog = () => api<AutomationCatalog>("/v1/automations-catalog");
export const convertAutomation = (x: string | object) => api<{ definition: Record<string, unknown>; yaml: string; valid: boolean; problems: string[] }>("/v1/automations/convert", { method: "POST", body: body(x) });
export interface AutomationDraft { definition: Record<string, unknown> | null; yaml?: string; problems: string[]; saved: false; note: string;
  dryRun: { startsWhen: string; steps: { id: string; kind: string; does: string; problem: string | null }[]; canRun: boolean; needsApproval: boolean; sendsOut: boolean; note: string } | null }
export const draftAutomation = (description: string) => api<AutomationDraft>("/v1/automations/draft", { method: "POST", body: JSON.stringify({ description }) });

// ---------- Library items (Workspace) ----------
export interface LibraryItem { id: string; title: string; kind: "prompt" | "macro" | "playbook" | "canned"; visibility: "private" | "team" | "shared"; team?: string | null; owner: string; tags: string[]; uses: number; version: number; updatedAt: number; preview: string; body?: string }
export const listLibraryItems = (opts: { kind?: string; q?: string; mine?: boolean } = {}) =>
  api<{ items: LibraryItem[] }>(`/v1/workspace/library-items?${new URLSearchParams({ ...(opts.kind ? { kind: opts.kind } : {}), ...(opts.q ? { q: opts.q } : {}), ...(opts.mine ? { mine: "true" } : {}) })}`).then((r) => r.items);
export const saveLibraryItem = (b: { title: string; body: string; kind: string; visibility?: string; tags?: string[] }) => api<LibraryItem>("/v1/workspace/library-items", { method: "POST", body: JSON.stringify(b) });
export const editLibraryItem = (id: string, b: Partial<{ title: string; body: string; visibility: string; tags: string[] }>) => api<LibraryItem>(`/v1/workspace/library-items/${id}`, { method: "PUT", body: JSON.stringify(b) });
export const getLibraryItem = (id: string) => api<LibraryItem>(`/v1/workspace/library-items/${id}`);
export const deleteLibraryItem = (id: string) => api<{ deleted: boolean }>(`/v1/workspace/library-items/${id}`, { method: "DELETE" });
export const takeLibraryItem = (id: string) => api<LibraryItem>(`/v1/workspace/library-items/${id}/use`, { method: "POST" });
export const suggestLibraryItems = (text: string) => api<{ suggestions: LibraryItem[] }>("/v1/workspace/library-items/suggest", { method: "POST", body: JSON.stringify({ text }) }).then((r) => r.suggestions);
export interface SpaceFileItem { id: string; spaceId: string; name: string; size: number; owner: string; createdAt: number; text?: string }
export const listSpaceFiles = (spaceId: string) => api<{ files: SpaceFileItem[] }>(`/v1/workspace/spaces/${spaceId}/files`).then((r) => r.files);
export const addSpaceFile = (spaceId: string, name: string, content: { text: string } | { dataBase64: string }) => api<SpaceFileItem>(`/v1/workspace/spaces/${spaceId}/files`, { method: "POST", body: JSON.stringify({ name, ...content }) });
export const deleteSpaceFile = (spaceId: string, fileId: string) => api<{ deleted: boolean }>(`/v1/workspace/spaces/${spaceId}/files/${fileId}`, { method: "DELETE" });
export const confirmPilotAction = (id: string) => api<PilotAction>(`/v1/workspace/actions/${id}/confirm`, { method: "POST" });
export const cancelPilotAction = (id: string) => api<PilotAction>(`/v1/workspace/actions/${id}/cancel`, { method: "POST" });

// ---------- The Builder's improvement loop ----------
export interface ImproveResult {
  findings: { days: number; conversations: number; causes: { cause: string; count: number }[]; reviewerFailures: Record<string, number>; examples: string[] };
  proposal: { specYaml: string; changes: string[]; warnings: string[] };
  tests: { verdict: string; safe: boolean; before?: { ran: boolean; passed?: boolean; counts?: { total: number; failed: number }; reason?: string }; after?: { ran: boolean; passed?: boolean; counts?: { total: number; failed: number }; reason?: string } };
  draftVersion: number | null; note: string;
}
export const improveAgent = (agentId: string, opts: { days?: number; focus?: string; createDraft?: boolean } = {}) =>
  api<ImproveResult>(`/v1/agents/${encodeURIComponent(agentId)}/improve`, { method: "POST", body: JSON.stringify(opts) });

// ---------- Organization settings and trust (Admin) ----------
export interface TenantLimitRow { value: number | null; source: "tenant" | "platform" | "none" }
export const getTenantLimits = () => api<{ tenant: string; limits: Record<string, TenantLimitRow> }>("/v1/tenant/limits");
export const getTenantProvider = () => api<{ tenant: string; own: boolean; baseUrl?: string; defaultModel?: string; where?: string; keyStored?: boolean }>("/v1/tenant/provider");
export interface ChannelRow { id: string; label: string; configured: boolean; inbound: string; note?: string }
export const getChannels = () => api<{ channels: ChannelRow[] }>("/v1/channels").then((r) => r.channels);
