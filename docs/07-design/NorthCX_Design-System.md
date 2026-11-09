# NorthCX Design System

Status: **Partly built**. Updated: 2026-11-09. Master for: the design system (early code in src/packages/ui).

## Brand
Name NorthCX: a fixed point that guides. Tone: calm, precise, trustworthy.

## Foundations
- **Colour:** deep navy primary, a single bright accent, neutral greys; semantic colours for pass/fail/warn. All text meets WCAG AA contrast.
- **Type:** one sans-serif family, one monospace for traces and code.
- **Spacing:** 4px base scale.
- **Radius and elevation:** small radii, minimal shadows.
- **Dark mode:** supported from the start through tokens.

## Components
Button, input, select, toggle, table, tabs, badge (status), toast, modal, code block, trace timeline, chat bubble, diff view.

## Status badges
`completed` green, `escalated` amber, `needs_approval` blue, `blocked` red.

## Accessibility
Keyboard navigable, visible focus, labelled controls, no colour-only meaning.

## Glass design system (proposed, 2026-11-09; an early version is in `src/packages/ui` on `main`, unfinished)
- **Surfaces:** translucent panels over a soft gradient, in light and dark. Where the system or the person asks for less transparency, or contrast is not enough, surfaces are solid. Text on any surface still meets WCAG AA.
- **Themes and preferences:** match device, light or dark; an accent colour with **fixed status colours** (ok, warn, bad, info never follow the accent); density (comfortable, compact); text size; high contrast; reduce motion. Applied through `data-theme`, `data-accent`, `data-density`, `data-text`, `data-contrast` and `data-motion` attributes; saved per browser first.
- **Shared across both apps:** one token set, one shell (left navigation, sub-tab row, top bar with search, notifications, availability, app switcher), one set of components. The Workspace uses six left items with sub-tabs; the Admin app uses grouped navigation (Operate, Build, Govern, Platform).
- **New components:** sub-tab row with count badges, command bar, plan card with numbered steps, steps timeline, citation chip, "what it used" popover, task-style switch, model-mode picker with destination shown, masked-field with reveal-with-reason, empty and error states with a next step.
- **Rules:** one meaning per word (Result is the chat's current work; Outputs are saved work); status is never colour only; every control is reachable by keyboard; mockups use invented data and say so.
