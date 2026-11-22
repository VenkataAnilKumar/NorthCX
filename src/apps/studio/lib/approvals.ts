/** Which tools the agent may use and which of them always wait for a person. A tool that changes things starts out needing a person's OK;
 *  the author can switch that off for a tool, and the screen says what that means. */
interface Choice { tools: string[]; always: string[] }

export function chooseTool(now: Choice, name: string, on: boolean, changesThings: boolean): Choice {
  if (!on) return { tools: now.tools.filter((t) => t !== name), always: now.always.filter((t) => t !== name) };
  if (now.tools.includes(name)) return now;
  return { tools: [...now.tools, name], always: changesThings && !now.always.includes(name) ? [...now.always, name] : now.always };
}

export function setAlways(now: Choice, name: string, on: boolean): Choice {
  const rest = now.always.filter((t) => t !== name);
  return { tools: now.tools, always: on ? [...rest, name] : rest };
}

/** The tools that change things and will run without a person: no rule of their own and not listed. (A tool with its own rule, such as a refund limit, is not listed here.) */
export function unguarded(now: Choice, catalog: { name: string; effect: string; approval?: boolean }[]): string[] {
  return now.tools.filter((t) => { const c = catalog.find((x) => x.name === t); return c?.effect === "write" && !c.approval && !now.always.includes(t); });
}
