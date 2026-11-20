const styles: Record<string, string> = {
  completed: "bg-[var(--ok-bg)] text-[var(--ok)]",
  escalated: "bg-[var(--warn-bg)] text-[var(--warn)]",
  in_review: "bg-[var(--info-bg)] text-[var(--info)]",
  needs_approval: "bg-[var(--info-bg)] text-[var(--info)]",
  pending: "bg-[var(--info-bg)] text-[var(--info)]",
  approved: "bg-[var(--ok-bg)] text-[var(--ok)]",
  rejected: "bg-[var(--bad-bg)] text-[var(--bad)]",
  blocked: "bg-[var(--bad-bg)] text-[var(--bad)]",
  live: "bg-[var(--ok-bg)] text-[var(--ok)]",
  publish: "bg-[var(--info-bg)] text-[var(--info)]",
  rollback: "bg-[var(--warn-bg)] text-[var(--warn)]",
  satisfied: "bg-[var(--ok-bg)] text-[var(--ok)]",
  passed: "bg-[var(--ok-bg)] text-[var(--ok)]",
  open: "bg-[var(--warn-bg)] text-[var(--warn)]",
  resolved: "bg-[var(--ok-bg)] text-[var(--ok)]",
  revoked: "bg-[var(--bad-bg)] text-[var(--bad)]",
  executing: "bg-[var(--info-bg)] text-[var(--info)]",
  executed: "bg-[var(--ok-bg)] text-[var(--ok)]",
  failed: "bg-[var(--bad-bg)] text-[var(--bad)]",
  expired: "bg-[var(--warn-bg)] text-[var(--warn)]",
};
const labels: Record<string, string> = { needs_approval: "Needs approval", in_review: "In review" };

export function StatusBadge({ status }: { status: string }) {
  const label = labels[status] ?? status.charAt(0).toUpperCase() + status.slice(1);
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status] ?? "bg-[var(--border)] text-[var(--muted)]"}`}>
      {label}
    </span>
  );
}
