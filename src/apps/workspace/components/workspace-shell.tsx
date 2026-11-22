"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { WORK_CHANGED, listApprovals, listHandoffs, listShadowDrafts, useLoad, useMe } from "@northcx/api-client";
import { AppShell, type NavItem } from "@northcx/ui";

const ADMIN_URL = process.env.NEXT_PUBLIC_ADMIN_URL ?? "http://localhost:3001";

/** Six left items with sub-tabs (decisions 157 and 162). Pages whose backend is not built yet say so on the page. */
export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { me, can } = useMe();
  const waiting = useLoad(async () => {
    try { return { approvals: (await listApprovals("pending")).length, handoffs: (await listHandoffs("open")).length }; } catch { return { approvals: 0, handoffs: 0 }; }
  }, []);
  const reviewsDrafts = can("shadow:review");
  const drafts = useLoad(async () => { try { return reviewsDrafts ? (await listShadowDrafts("pending")).length : 0; } catch { return 0; } }, [reviewsDrafts]);
  useEffect(() => {  // a decision made on a page changes the waiting counts in the menu
    const again = () => { waiting.reload(); drafts.reload(); };
    window.addEventListener(WORK_CHANGED, again);
    return () => window.removeEventListener(WORK_CHANGED, again);
  }, [waiting.reload, drafts.reload]);
  const lead = can("reviews:write") || can("insights:read"); // Team is for leads and reviewers only
  const nav: NavItem[] = [
    { href: "/", label: "Home", icon: "Home" },
    { href: "/pilot", label: "Pilot", icon: "Pilot" },
    { href: "/inbox", label: "Work", icon: "Work", children: [
      { href: "/inbox", label: "Inbox", badge: waiting.data?.handoffs },
      { href: "/approvals", label: "Approvals", badge: waiting.data?.approvals },
      ...(reviewsDrafts ? [{ href: "/drafts", label: "Drafts", badge: drafts.data ?? undefined }] : []),
      { href: "/customers", label: "Customers" },
    ] },
    { href: "/assistants", label: "Assist", icon: "Assist", children: [
      { href: "/assistants", label: "Assistants" },
      { href: "/search", label: "Search" },
      { href: "/library", label: "Library" },
    ] },
    { href: "/outputs", label: "Create", icon: "Create", children: [
      { href: "/outputs", label: "Outputs" },
      { href: "/spaces", label: "Spaces" },
      { href: "/automations", label: "Automations" },
    ] },
    ...(lead ? [{ href: "/quality", label: "Team", icon: "Team" as const, children: [
      { href: "/quality", label: "Quality" },
      { href: "/performance", label: "Performance" },
    ] }] : []),
  ];
  return (
    <AppShell appName="Workspace" nav={nav} path={path} Link={Link}
      switcher={[{ label: "Workspace", href: "/", current: true }, { label: "Admin", href: ADMIN_URL }]}
      user={me ? (me.openMode ? <span className="text-[var(--warn)]">Open mode: no authentication is configured on the server.</span> : <><Link className="underline" href="/settings">{me.name}</Link> ({me.role.replace("_", " ")})</>) : null}>
      {children}
    </AppShell>
  );
}
