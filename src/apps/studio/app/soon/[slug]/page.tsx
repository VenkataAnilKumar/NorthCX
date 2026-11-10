"use client";
import { use } from "react";
import { ComingSoon } from "@northcx/ui";

/** Honest placeholders for Admin pages whose backend is not built yet; nothing here shows made-up data. */
const PAGES: Record<string, { title: string; what: string; needs: string }> = {
  "trust": { title: "Trust and reliability", what: "Security posture, status and reliability figures for the organization.", needs: "the trust centre (E16)" },
  "channels": { title: "Channels", what: "Where agents talk to customers, with a health view per channel.", needs: "a Channels admin view over the existing adapters" },
  "systems": { title: "Systems", what: "Connected business systems and the permissions each agent has on them.", needs: "native connectors (E4)" },
  "org": { title: "Organization settings", what: "Name, defaults, retention and feature switches for the organization.", needs: "multi-tenancy (E2)" },
  "memory": { title: "Memory", what: "What assistants remember about you, with per-item delete.", needs: "staff memory (E5.5)" },
  "connectors": { title: "Connectors", what: "Your own connected accounts and what each can be used for.", needs: "connectors (E4)" },
  "mcp": { title: "MCP servers", what: "Tool servers you or your organization have connected.", needs: "an MCP client (E9)" },
  "notifications": { title: "Notifications", what: "Choose what reaches you and where.", needs: "notification delivery (E5)" },
  "privacy": { title: "Privacy and data", what: "Export or erase your data and set your retention.", needs: "personal data controls (E5.5)" },
  "limits": { title: "Usage and limits", what: "Your own usage and the limits that apply to you.", needs: "usage metering (E10)" },
  "keys": { title: "API keys", what: "Keys you create for yourself, limited to your own access.", needs: "personal keys (E3)" },
  "security": { title: "Security and sessions", what: "Where you are signed in, with sign-out for each session.", needs: "sessions (E3)" },
};

export default function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const p = PAGES[slug];
  if (!p) return <ComingSoon title="Page not found" what="This page does not exist." needs="nothing; check the address" />;
  return <ComingSoon title={p.title} what={p.what} needs={p.needs} />;
}
