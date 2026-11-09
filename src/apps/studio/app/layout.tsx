import type { Metadata } from "next";
import "./globals.css";
import { ThemeScript } from "@northcx/ui";
import { StudioShell } from "@/components/studio-shell";

export const metadata: Metadata = { title: "NorthCX Admin", description: "Supervised customer-experience agents: settings and admin" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head><ThemeScript /></head>
      <body>
        <StudioShell>{children}</StudioShell>
      </body>
    </html>
  );
}
