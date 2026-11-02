export function Loading() {
  return <p role="status" className="text-sm text-muted">Loading…</p>;
}
export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-[var(--bad)] bg-[var(--bad-bg)] p-3 text-sm text-[var(--bad)]">
      {message}
      {onRetry && <button onClick={onRetry} className="ml-3 underline">Retry</button>}
      {message.includes("401") || message.toLowerCase().includes("api key") ? <span className="ml-2">Set the key in Settings.</span> : null}
    </div>
  );
}
export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted">{children}</p>;
}
export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}
