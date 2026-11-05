import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/nav";

export const metadata: Metadata = { title: "NorthCX", description: "Supervised customer-experience agents" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-4 p-4 md:flex-row md:gap-8 md:p-6">
          <aside className="md:w-52 md:shrink-0">
            <div className="mb-4 text-lg font-bold text-primary">NorthCX</div>
            <Nav />
          </aside>
          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
