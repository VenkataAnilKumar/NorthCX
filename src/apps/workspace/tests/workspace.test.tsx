import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppShell, applyPrefs, ComingSoon, DEFAULT_PREFS, StatTile } from "@northcx/ui";

const Link = ({ href, children, className, ...rest }: { href: string; children?: React.ReactNode; className?: string }) => createElement("a", { href, className, ...rest }, children);

describe("shared glass shell", () => {
  it("marks the current page, shows badges and flags tabs that are not built yet", () => {
    const html = renderToStaticMarkup(createElement(AppShell, {
      appName: "Workspace", path: "/inbox", Link,
      nav: [{ href: "/inbox", label: "Work", icon: "Work", children: [{ href: "/inbox", label: "Inbox", badge: 3 }, { href: "/customers", label: "Customers", soon: true }] }],
      switcher: [{ label: "Workspace", href: "/", current: true }, { label: "Admin", href: "http://localhost:3001" }],
      children: createElement("p", null, "body"),
    }));
    expect(html).toContain('aria-current="page"');
    expect(html).toContain('aria-label="3 waiting"');
    expect(html).toContain("soon");
    expect(html).toContain("Switch app");
  });

  it("says what a missing tab will do and what it waits for, with no made-up data", () => {
    const html = renderToStaticMarkup(createElement(ComingSoon, { title: "Workflows", what: "Multi-step work.", needs: "automations (E8)" }));
    expect(html).toContain("Not available yet");
    expect(html).toContain("Waiting for: automations (E8)");
  });

  it("renders a stat tile with its hint", () => {
    expect(renderToStaticMarkup(createElement(StatTile, { label: "Open", value: 2, hint: "waiting" }))).toContain("waiting");
  });
});

describe("preferences", () => {
  it("sets only the attributes that differ from the defaults", () => {
    const root = document.createElement("html");
    applyPrefs({ ...DEFAULT_PREFS, theme: "dark", accent: "teal", contrast: "high" }, root);
    expect(root.getAttribute("data-theme")).toBe("dark");
    expect(root.getAttribute("data-accent")).toBe("teal");
    expect(root.getAttribute("data-contrast")).toBe("high");
    expect(root.hasAttribute("data-density")).toBe(false);
    applyPrefs(DEFAULT_PREFS, root);
    expect(root.getAttributeNames()).toEqual([]);
  });
});
