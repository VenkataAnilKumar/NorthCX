"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { listApprovals, listHandoffs, useLoad, useMe } from "@northcx/api-client";
import { AppShell, type NavItem, type SubItem } from "@northcx/ui";

const WORKSPACE_URL = process.env.NEXT_PUBLIC_WORKSPACE_URL ?? "http://localhost:3002";
const soon = (slug: string, label: string): SubItem => ({ href: `/soon/${slug}`, label, soon: true });

/** Six left items with sub-tabs (decision 157); text-only sub-tabs, icons on the left items only. */
export function StudioShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { me, can } = useMe();
  const waiting = useLoad(async () => {
    try { return { approvals: (await listApprovals("pending")).length, handoffs: (await listHandoffs("open")).length }; } catch { return { approvals: 0, handoffs: 0 }; }
  }, []);
  const any = (...p: string[]) => p.some(can);
  const operate: SubItem[] = [
    { href: "/conversations", label: "Conversations" },
    { href: "/handoffs", label: "Hand-offs", badge: waiting.data?.handoffs },
    { href: "/approvals", label: "Approvals", badge: waiting.data?.approvals },
    ...(any("reviews:write", "traces:read") ? [{ href: "/review", label: "Review and QA" }] : []),
    ...(can("monitor:read") ? [{ href: "/monitoring", label: "Monitoring" }] : []),
    ...(can("insights:read") ? [{ href: "/insights", label: "Analytics" }] : []),
  ];
  const build: SubItem[] = [
    { href: "/agents", label: "Agents" },
    { href: "/hub", label: "Agent Hub" },
    { href: "/agents/build", label: "Builder" },
    ...(can("knowledge:read") ? [{ href: "/knowledge", label: "Library" }] : []),
    { href: `${WORKSPACE_URL}/automations`, label: "Automations" }, // lives in the Workspace
    { href: "/simulations", label: "Simulations" },
    { href: "/models", label: "Models and budgets" },
    { href: "/chat", label: "Test console" },
  ];
  const govern: SubItem[] = [
    { href: "/people", label: "People and groups" },
    ...(any("keys:manage", "audit:read") ? [{ href: "/access", label: "Access keys" }, { href: "/access#audit", label: "Audit and activity" }] : []),
    { href: "/policies", label: "Policies" },
    { href: "/trust", label: "Trust and reliability" },
    ...(can("audit:read") ? [{ href: "/residency", label: "Data residency" }] : []),
  ];
  const platform: SubItem[] = [{ href: "/channels", label: "Channels" }, soon("systems", "Systems"), { href: "/usage", label: "Usage and billing" }, { href: "/org", label: "Organization settings" }];
  const personal: SubItem[] = [
    { href: "/profile", label: "Profile" },
    { href: "/preferences", label: "Preferences" },
    { href: "/memory", label: "Memory" }, soon("connectors", "Connectors"), soon("mcp", "MCP servers"), soon("notifications", "Notifications"),
    { href: "/privacy", label: "Privacy and data" }, soon("limits", "Usage and limits"), { href: "/access", label: "API keys" }, soon("security", "Security and sessions"),
    { href: "/settings", label: "Connection" },
  ];
  const nav: NavItem[] = [
    { href: "/", label: "Overview", icon: "Overview" },
    { href: operate[0].href, label: "Operate", icon: "Operate", children: operate },
    { href: build[0].href, label: "Build", icon: "Build", children: build },
    { href: govern[0].href, label: "Govern", icon: "Govern", children: govern },
    { href: platform[0].href, label: "Platform", icon: "Platform", children: platform },
    { href: personal[0].href, label: "Personal", icon: "Personal", children: personal },
  ];
  return (
    <AppShell appName="Admin" nav={nav} path={path} Link={Link}
      switcher={[{ label: "Admin", href: "/", current: true }, { label: "Workspace", href: WORKSPACE_URL }]}
      user={me ? (me.openMode ? <span className="text-[var(--warn)]">Open mode: no authentication is configured on the server.</span> : <>Signed in as <strong>{me.name}</strong> ({me.role.replace("_", " ")})</>) : null}>
      {children}
    </AppShell>
  );
}
