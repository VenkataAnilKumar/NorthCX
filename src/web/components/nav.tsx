"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMe } from "@/lib/me";

const items: { href: string; label: string; any?: string[] }[] = [
  { href: "/", label: "Overview" },
  { href: "/chat", label: "Test console" },
  { href: "/conversations", label: "Conversations" },
  { href: "/simulations", label: "Simulations" },
  { href: "/handoffs", label: "Handoffs" },
  { href: "/approvals", label: "Approvals" },
  { href: "/agents", label: "Agents" },
  { href: "/access", label: "Access and audit", any: ["keys:manage", "audit:read"] },
  { href: "/settings", label: "Settings" },
];

export function Nav() {
  const path = usePathname();
  const { me, can } = useMe();
  return (
    <nav aria-label="Main" className="flex gap-1 overflow-x-auto md:flex-col">
      {items.filter((i) => !i.any || i.any.some(can)).map((i) => {
        const active = i.href === "/" ? path === "/" : path.startsWith(i.href);
        return (
          <Link key={i.href} href={i.href} aria-current={active ? "page" : undefined}
            className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm ${active ? "bg-primary font-medium text-primary-text" : "text-muted hover:bg-border/40"}`}>
            {i.label}
          </Link>
        );
      })}
      {me && (
        <p aria-label="Signed in as" className="mt-3 hidden px-3 text-xs text-muted md:block">
          {me.openMode ? <span className="text-[var(--warn)]">Open mode: no authentication is configured on the server.</span>
            : <>Signed in as <strong>{me.name}</strong> ({me.role.replace("_", " ")})</>}
        </p>
      )}
    </nav>
  );
}
