"use client";
import Link from "next/link";
import { automations, customersEnabled, getAlerts, getMonitorSummary, getResidency, useLoad } from "@northcx/api-client";
import { ErrorBox, GlassCard, Loading, PageHeader, StatTile } from "@northcx/ui";

type Row = { label: string; state: "good" | "warn" | "bad" | "off"; text: string; href?: string };
const CLS = { good: "text-[var(--good)]", warn: "text-[var(--warn)]", bad: "text-[var(--bad)]", off: "text-muted" } as const;
const MARK = { good: "OK", warn: "Check", bad: "Problem", off: "Off" } as const;

/** Reads only figures the server already reports; nothing here is estimated or invented. */
export default function Trust() {
  const { data, error, loading, reload } = useLoad(async () => {
    const [monitor, alerts, residency, customers, autos] = await Promise.all([
      getMonitorSummary().catch(() => null), getAlerts().catch(() => null), getResidency().catch(() => null),
      customersEnabled().catch(() => null), automations().catch(() => null),
    ]);
    return { monitor, alerts, residency, customers, autos };
  }, []);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  const { monitor, alerts, residency, customers, autos } = data;
  const critical = monitor ? Object.values(monitor.counts).reduce((n, c) => n + (c.critical ?? 0), 0) : 0;
  const rows: Row[] = [
    residency ? { label: "Data residency", state: !residency.configured ? "warn" : residency.compliant ? "good" : "bad", href: "/residency",
      text: !residency.configured ? "No residency file set, so destinations are listed but not checked." : residency.compliant ? `Every destination is allowed (region ${residency.region}).` : `${residency.problems.length} destination problem(s).` }
      : { label: "Data residency", state: "off", text: "Not available to your role.", href: "/residency" },
    alerts ? { label: "Alerts", state: !alerts.enabled || !alerts.webhook ? "warn" : (alerts.undelivered ?? 0) > 0 ? "bad" : "good", href: "/monitoring",
      text: !alerts.enabled ? "Alerting is off." : `${alerts.active?.length ?? 0} active, ${alerts.undelivered ?? 0} not delivered${alerts.webhook ? "" : "; no webhook set"}.` }
      : { label: "Alerts", state: "off", text: "Not available to your role.", href: "/monitoring" },
    monitor ? { label: "Always-on monitoring", state: critical > 0 ? "bad" : "good", href: "/monitoring", text: `${monitor.total} finding(s), ${critical} critical.` }
      : { label: "Always-on monitoring", state: "off", text: "Not available to your role.", href: "/monitoring" },
    { label: "Customer view (Workspace)", state: customers ? (customers.enabled ? "good" : "off") : "off", text: customers ? (customers.enabled ? "On: staff can look up a customer by exact identifier; every open is recorded." : "Switched off for the organization.") : "Not available to your role." },
    { label: "Automations", state: autos ? (autos.enabled ? "good" : "off") : "off", text: autos ? (autos.enabled ? `On: ${autos.automations.length} routine(s). Each routine and the whole organization has a kill switch.` : "Kill switch is on: no routine runs.") : "Not available to your role." },
  ];
  return (
    <>
      <PageHeader title="Trust and reliability" subtitle="The live state of the controls that protect customers and the organization. Every line is read from the server now." />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <StatTile label="Findings" value={monitor ? monitor.total : "n/a"} hint="from always-on monitoring" />
        <StatTile label="Critical" value={monitor ? critical : "n/a"} hint="needs a person" />
        <StatTile label="Undelivered alerts" value={alerts ? (alerts.undelivered ?? 0) : "n/a"} hint="alerts that did not reach you" />
      </div>
      <GlassCard title="Controls">
        <ul className="divide-y divide-border text-sm">
          {rows.map((r) => (
            <li key={r.label} className="flex flex-wrap items-baseline gap-x-3 py-2">
              <span className={`w-16 font-medium ${CLS[r.state]}`}>{MARK[r.state]}</span>
              <span className="w-56 font-medium">{r.href ? <Link className="underline" href={r.href}>{r.label}</Link> : r.label}</span>
              <span className="text-muted">{r.text}</span>
            </li>))}
        </ul>
      </GlassCard>
      <p className="mt-3 text-xs text-muted">Not shown because they are not measured here: uptime history and an outside security assessment. See the owner runbooks and the penetration-test brief in the docs.</p>
    </>
  );
}
