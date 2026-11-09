"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { listApprovals, listHandoffs, useLoad, useMe } from "@northcx/api-client";
import { AppShell, type NavGroup } from "@northcx/ui";

const ADMIN_URL = process.env.NEXT_PUBLIC_ADMIN_URL ?? "http://localhost:3001";

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { me, can } = useMe();
  const waiting = useLoad(async () => {
    try { return { approvals: (await listApprovals("pending")).length, handoffs: (await listHandoffs("open")).length }; } catch { return { approvals: 0, handoffs: 0 }; }
  }, []);
  const groups: NavGroup[] = [
    { items: [{ href: "/", label: "Home", icon: "⌂" }] },
    { label: "Work", items: [
      { href: "/threads", label: "Threads", icon: "🧵", badge: waiting.data?.handoffs },
      { href: "/approvals", label: "Approvals", icon: "✅", badge: waiting.data?.approvals },
      { href: "/customers", label: "Customers", icon: "👤", soon: true },
    ] },
    { label: "Assist", items: [
      { href: "/chat", label: "Chat", icon: "💬" },
      { href: "/assistants", label: "Assistants", icon: "🤖" },
      { href: "/search", label: "Search", icon: "🔍" },
      ...(can("knowledge:read") ? [{ href: "/knowledge", label: "Knowledge", icon: "📚" }] : []),
    ] },
    { label: "Create", items: [
      { href: "/artifacts", label: "Artifacts", icon: "📄", soon: true },
      { href: "/projects", label: "Projects", icon: "📁", soon: true },
      { href: "/workflows", label: "Workflows", icon: "🔀", soon: true },
      { href: "/scheduled", label: "Scheduled", icon: "⏱", soon: true },
    ] },
    { label: "Team", items: [
      { href: "/reviews", label: "Reviews", icon: "📝", soon: true },
      { href: "/insights", label: "Insights", icon: "📈", soon: true },
    ] },
    { label: "You", items: [{ href: "/settings", label: "Settings", icon: "⚙" }] },
  ];
  return (
    <AppShell appName="Workspace" nav={groups} path={path} Link={Link}
      switcher={[{ label: "Workspace", href: "/", current: true }, { label: "Admin", href: ADMIN_URL }]}
      user={me ? (me.openMode ? <span className="text-[var(--warn)]">Open mode: no authentication is configured on the server.</span> : <>Signed in as <strong>{me.name}</strong> ({me.role.replace("_", " ")})</>) : null}
      top={<span className="text-sm text-muted">Your workspace</span>}>
      {children}
    </AppShell>
  );
}
