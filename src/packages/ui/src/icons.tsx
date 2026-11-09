import type { ReactNode } from "react";

/** The NorthCX tab icons: original line drawings on a 24 px grid (1.6 px stroke, round caps, no fill), no third-party icon set.
 *  Icons appear on the six left items of each app and nowhere else; every use also carries a text label or an accessible name. */
export type IconName =
  | "Home" | "Pilot" | "Work" | "Assist" | "Create" | "Team"
  | "Overview" | "Operate" | "Build" | "Govern" | "Platform" | "Personal"
  | "Expand" | "Collapse" | "Menu" | "Search";

const PATHS: Record<IconName, ReactNode> = {
  Home: <path d="M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1z" />,
  Pilot: <><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /><path d="M18.5 16.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" /></>,
  Work: <><path d="M4 13l2-7h12l2 7v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" /><path d="M4 13h4l1 2h6l1-2h4" /></>,
  Assist: <><path d="M5 5h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-7l-4 3.5V15H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" /><path d="M9 10h.01M12 10h.01M15 10h.01" /></>,
  Create: <><path d="M12 4l8 4-8 4-8-4z" /><path d="M4 12l8 4 8-4" /><path d="M4 16l8 4 8-4" /></>,
  Team: <path d="M5 19v-7M12 19V5M19 19v-4" />,
  Overview: <><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></>,
  Operate: <path d="M3 12h4l3-7 4 14 3-7h4" />,
  Build: <><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" /><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" /></>,
  Govern: <><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" /><path d="M9 12l2 2 4-4" /></>,
  Platform: <><rect x="4" y="5" width="16" height="5" rx="1.5" /><rect x="4" y="14" width="16" height="5" rx="1.5" /><path d="M8 7.5h.01M8 16.5h.01" /></>,
  Personal: <><circle cx="12" cy="8" r="4" /><path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" /></>,
  Expand: <path d="M9 6l6 6-6 6" />,
  Collapse: <path d="M15 6l-6 6 6 6" />,
  Menu: <path d="M5 8h14M5 12h14M5 16h14" />,
  Search: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4-4" /></>,
};

export function NavIcon({ name, className = "rail-icon" }: { name: IconName; className?: string }) {
  return <svg viewBox="0 0 24 24" className={className} aria-hidden="true" focusable="false">{PATHS[name]}</svg>;
}
export const ICON_NAMES = Object.keys(PATHS) as IconName[];
