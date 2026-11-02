"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/", label: "Overview" },
  { href: "/chat", label: "Test console" },
  { href: "/conversations", label: "Conversations" },
  { href: "/simulations", label: "Simulations" },
  { href: "/handoffs", label: "Handoffs" },
  { href: "/approvals", label: "Approvals" },
  { href: "/agents", label: "Agents" },
  { href: "/settings", label: "Settings" },
];

export function Nav() {
  const path = usePathname();
  return (
    <nav aria-label="Main" className="flex gap-1 overflow-x-auto md:flex-col">
      {items.map((i) => {
        const active = i.href === "/" ? path === "/" : path.startsWith(i.href);
        return (
          <Link key={i.href} href={i.href} aria-current={active ? "page" : undefined}
            className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm ${active ? "bg-primary font-medium text-primary-text" : "text-muted hover:bg-border/40"}`}>
            {i.label}
          </Link>
        );
      })}
    </nav>
  );
}
