import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { activeItem, AppShell, applyPrefs, ComingSoon, DEFAULT_PREFS, StatTile } from "@northcx/ui";

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

describe("navigation helpers", () => {
  const nav = [{ href: "/", label: "Home", icon: "Home" as const }, { href: "/inbox", label: "Work", icon: "Work" as const, children: [{ href: "/inbox", label: "Inbox" }, { href: "/approvals", label: "Approvals" }] }];
  it("finds the item and sub-tab that own a path, including nested paths", () => {
    expect(activeItem(nav, "/approvals/x").item?.label).toBe("Work");
    expect(activeItem(nav, "/approvals").sub?.label).toBe("Approvals");
    expect(activeItem(nav, "/").item?.label).toBe("Home");
    expect(activeItem(nav, "/nowhere").item).toBeUndefined();
  });
});
