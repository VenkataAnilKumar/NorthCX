import { type ToolCardData, toolLabel } from "@/lib/console-steps";

export interface HeldAction { id: string; tool: string; reason: string; input: string }
export type Decision = { state: "waiting" } | { state: "approved" | "rejected"; by: string | null } | { state: "gone" };

export function ToolCard({ card }: { card: ToolCardData }) {
  return (
    <div role="group" aria-label={`Tool: ${card.label}`} className="rounded-lg border border-border bg-bg px-3 py-2 text-xs">
      <p className="font-medium">{card.label}</p>
      <p className="text-muted">Asked with: {card.input}</p>
      {card.outcome === "done" && <p className="text-muted">Answer: {card.detail}</p>}
      {card.outcome === "held" && <p className="text-[var(--warn)]">Held for a person: {card.detail}</p>}
      {card.outcome === "unfinished" && <p className="text-muted">No answer was recorded.</p>}
    </div>
  );
}

export function ApprovalCard({ action, decision, canDecide, busy, onDecide }: { action: HeldAction; decision: Decision; canDecide: boolean; busy: boolean; onDecide: (approved: boolean) => void }) {
  const label = toolLabel(action.tool);
  return (
    <div role="group" aria-label={`Approval: ${label}`} className="rounded-lg border border-[var(--info)] bg-surface px-3 py-2 text-sm">
      <p className="font-medium">{decision.state === "waiting" ? "Waiting for a person to decide" : "Held for a person"}: {label}</p>
      <p className="text-xs text-muted">Would run with: {action.input}</p>
      <p className="text-xs text-muted">Why it waits: {action.reason}</p>
      {decision.state === "waiting" && (canDecide ? (
        <div className="mt-2 flex gap-2">
          <button disabled={busy} onClick={() => onDecide(true)} aria-label={`Approve ${label}`} className="btn btn-primary">{busy ? "Working…" : "Approve"}</button>
          <button disabled={busy} onClick={() => onDecide(false)} aria-label={`Reject ${label}`} className="btn">Reject</button>
        </div>
      ) : <p className="mt-1 text-xs text-muted">Your role cannot decide approvals. Ask someone who can, or open Approvals.</p>)}
      {(decision.state === "approved" || decision.state === "rejected") && <p role="status" className="mt-1 text-xs">{decision.state === "approved" ? "Approved" : "Rejected"}{decision.by ? ` by ${decision.by}` : ""}. The customer is told through their channel.</p>}
      {decision.state === "gone" && <p role="status" className="mt-1 text-xs text-[var(--warn)]">No longer waiting: it was decided somewhere else or it expired. Nothing ran from here.</p>}
    </div>
  );
}
