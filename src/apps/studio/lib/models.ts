import type { ModelQualification, ModelsOverview } from "@northcx/api-client";

export const TIER_NAME: Record<string, string> = { local: "Local, on your servers", "private-cloud": "Private cloud, your account", "public-cloud": "Public cloud, the provider's service" };

export interface ModelChoice { value: string; label: string; tier: string | null }

/** One choice per configured provider, in the `provider:model` form the agent definition stores, plus the value already set if it is not one of them. */
export function modelChoices(overview: ModelsOverview | null, current: string): ModelChoice[] {
  const out: ModelChoice[] = (overview?.providers ?? []).filter((p) => p.defaultModel).map((p) => ({ value: `${p.name}:${p.defaultModel}`, label: `${p.defaultModel} (${p.name})`, tier: TIER_NAME[p.tier] ?? p.tier }));
  if (current && !out.some((c) => c.value === current)) out.push({ value: current, label: current, tier: null });
  return out;
}

/** What to tell an author about one model for this agent: the latest qualification run for exactly that model, or that there is none. */
export function qualificationNote(model: string, results: ModelQualification[], required: boolean): string {
  if (!model) return required ? "The server default is used. A model serves customers only after it passes this agent's scenarios; check the model you want below." : "The server default is used.";
  const mine = results.filter((q) => q.model === model).sort((a, b) => b.createdAt - a.createdAt)[0];
  if (!mine) return "Not qualified yet: no real-model run of this agent's scenarios has been recorded for this model.";
  const day = new Date(mine.createdAt * 1000).toISOString().slice(0, 10);
  const counts = `${mine.required.passed} of ${mine.required.total} required scenarios passed`;
  return mine.qualified ? `Qualified on ${day}: ${counts}.` : `Did not qualify on ${day}: ${counts}${mine.reasons.length ? `. ${mine.reasons[0]}` : ""}.`;
}
