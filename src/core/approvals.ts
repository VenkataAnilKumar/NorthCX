import { randomUUID } from "node:crypto";

export type ApprovalState = "pending" | "approved" | "rejected";
export interface Approval {
  id: string;
  traceId: string;
  sessionId: string;
  tool: string;
  input: unknown;
  reason: string;
  state: ApprovalState;
  createdAt: number;
  decidedBy?: string;
  decidedAt?: number;
}

/** Persists pending approvals so reviewers can act on them. Resuming a run after a decision is not implemented yet. */
export class ApprovalStore {
  private items = new Map<string, Approval>();
  add(a: Omit<Approval, "id" | "state" | "createdAt">): Approval {
    const item: Approval = { ...a, id: randomUUID(), state: "pending", createdAt: Date.now() };
    this.items.set(item.id, item);
    return item;
  }
  get(id: string) { return this.items.get(id); }
  list(state?: ApprovalState) { return [...this.items.values()].filter((a) => !state || a.state === state); }
  decide(id: string, approved: boolean, by: string): Approval {
    const a = this.items.get(id);
    if (!a) throw new Error(`Unknown approval ${id}`);
    if (a.state !== "pending") throw new Error(`Approval ${id} already ${a.state}`);
    a.state = approved ? "approved" : "rejected";
    a.decidedBy = by;
    a.decidedAt = Date.now();
    return a;
  }
}
