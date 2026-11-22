"use client";
import { listQualifications, modelsOverview, useLoad } from "@northcx/api-client";
import { modelChoices, qualificationNote } from "@/lib/models";

export function ModelPicker({ agentId, value, onChange, className }: { agentId: string; value: string; onChange: (v: string) => void; className: string }) {
  const overview = useLoad(() => modelsOverview().catch(() => null));
  const results = useLoad(() => listQualifications(agentId).catch(() => []));
  const choices = modelChoices(overview.data ?? null, value);
  const tier = choices.find((c) => c.value === value)?.tier;
  const required = overview.data?.routing?.qualification.required ?? false;
  return (
    <div className="text-sm">
      <label>Model
        <select value={value} onChange={(e) => onChange(e.target.value)} className={className}>
          <option value="">Server default</option>
          {choices.map((c) => <option key={c.value} value={c.value}>{c.label}{c.tier ? `, ${c.tier}` : ""}</option>)}
        </select>
      </label>
      <p className="mt-1 text-xs text-muted">{tier ? `${tier}. ` : ""}{qualificationNote(value, results.data ?? [], required)}</p>
    </div>
  );
}
