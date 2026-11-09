"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { listApprovals, listHandoffs, useLoad, useMe } from "@northcx/api-client";
import { AppShell, type NavGroup } from "@northcx/ui";

const WORKSPACE_URL = process.env.NEXT_PUBLIC_WORKSPACE_URL ?? "http://localhost:3002";

export function StudioShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { me, can } = useMe();
  // Counts for the badges; a failure just means no badge.
  const waiting = useLoad(async () => {
    try { return { approvals: (await listApprovals("pending")).length, handoffs: (await listHandoffs("open")).length }; } catch { return { approvals: 0, handoffs: 0 }; }
  }, []);
  const any = (...p: string[]) => p.some(can);
  const groups: NavGroup[] = [
    { label: "Operate", items: [
      { href: "/", label: "Overview", icon: "◧" },
      { href: "/conversations", label: "Conversations", icon: "💬" },
      { href: "/handoffs", label: "Handoffs", icon: "🧵", badge: waiting.data?.handoffs },
      { href: "/approvals", label: "Approvals", icon: "✅", badge: waiting.data?.approvals },
      ...(any("reviews:write", "traces:read") ? [{ href: "/review", label: "Review", icon: "📝" }] : []),
      ...(can("monitor:read") ? [{ href: "/monitoring", label: "Monitoring", icon: "📡" }] : []),
      ...(can("insights:read") ? [{ href: "/insights", label: "Insights", icon: "📈" }] : []),
    ] },
    { label: "Build", items: [
      { href: "/agents", label: "Agents", icon: "🤖" },
      { href: "/hub", label: "Agent Hub", icon: "🧩" },
      ...(can("knowledge:read") ? [{ href: "/knowledge", label: "Knowledge", icon: "📚" }] : []),
      { href: "/simulations", label: "Simulations", icon: "🧪" },
      { href: "/chat", label: "Test console", icon: "⌨" },
    ] },
    { label: "Govern", items: [
      ...(any("keys:manage", "audit:read") ? [{ href: "/access", label: "Access and audit", icon: "🔑" }] : []),
      ...(can("audit:read") ? [{ href: "/residency", label: "Data residency", icon: "🌍" }] : []),
    ] },
    { label: "Personal", items: [
      { href: "/profile", label: "Profile", icon: "👤" },
      { href: "/preferences", label: "Preferences", icon: "🎨" },
      { href: "/settings", label: "Settings", icon: "⚙" },
    ] },
  ];
  return (
    <AppShell appName="Admin" nav={groups} path={path} Link={Link}
      switcher={[{ label: "Admin", href: "/", current: true }, { label: "Workspace", href: WORKSPACE_URL }]}
      user={me ? (me.openMode ? <span className="text-[var(--warn)]">Open mode: no authentication is configured on the server.</span> : <>Signed in as <strong>{me.name}</strong> ({me.role.replace("_", " ")})</>) : null}
      top={<span className="text-sm text-muted">Settings and admin</span>}>
      {children}
    </AppShell>
  );
}
