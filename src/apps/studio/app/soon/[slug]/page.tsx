"use client";
import { use } from "react";
import { ComingSoon } from "@northcx/ui";

/** Honest placeholders for Admin pages whose backend is not built yet; nothing here shows made-up data. */
const PAGES: Record<string, { title: string; what: string; needs: string }> = {
  "systems": { title: "Systems", what: "Connected business systems and the permissions each agent has on them.", needs: "native connectors (E4)" },
  "connectors": { title: "Connectors", what: "Your own connected accounts and what each can be used for.", needs: "connectors (E4)" },
  "mcp": { title: "MCP servers", what: "Tool servers you or your organization have connected.", needs: "an MCP client (E9)" },
  "notifications": { title: "Notifications", what: "Choose what reaches you and where.", needs: "notification delivery (E5)" },
  "limits": { title: "Usage and limits", what: "Your own usage and the limits that apply to you.", needs: "usage metering (E10)" },
  "security": { title: "Security and sessions", what: "Where you are signed in, with sign-out for each session.", needs: "sessions (E3)" },
};

export default function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const p = PAGES[slug];
  if (!p) return <ComingSoon title="Page not found" what="This page does not exist." needs="nothing; check the address" />;
  return <ComingSoon title={p.title} what={p.what} needs={p.needs} />;
}
