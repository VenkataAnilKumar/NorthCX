import type { Metadata } from "next";
import "./globals.css";
import { ThemeScript } from "@northcx/ui";
import { WorkspaceShell } from "@/components/workspace-shell";

export const metadata: Metadata = { title: "NorthCX Workspace", description: "Your workspace for customer conversations, approvals and assistants" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head><ThemeScript /></head>
      <body>
        <WorkspaceShell>{children}</WorkspaceShell>
      </body>
    </html>
  );
}
