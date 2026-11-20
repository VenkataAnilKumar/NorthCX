import type { Trace, TraceEvent } from "@northcx/api-client";
import { plainStep } from "./console-steps";

export interface Frame { traceId: string; event: TraceEvent; sentence: string; turn: number | null }
export interface Line { kind: "customer" | "agent" | "note" | "tool"; text: string; turn: number | null; answer?: string }

/** The frames of a stored conversation: every event a person can read, from every trace, in the order it happened.
 *  A customer message is tied to its turn number by walking the turns in order and matching the words. */
export function buildFrames(traces: Trace[], turns: { turn: number; message: string }[] = []): Frame[] {
  const ordered = [...traces].filter((t) => t.events.length).sort((a, b) => a.events[0].t - b.events[0].t);
  const frames: Frame[] = [];
  let next = 0;
  for (const t of ordered) {
    for (const event of t.events) {
      const sentence = plainStep(event);
      if (sentence === null) continue;
      let turn: number | null = null;
      if (event.type === "user" && next < turns.length && turns[next].message === event.data.message) turn = turns[next++].turn;
      frames.push({ traceId: t.id, event, sentence, turn });
    }
  }
  return frames;
}

/** The conversation as it stood after frame `index`: what the customer and the agent said, tools used and notes. */
export function conversationAt(frames: Frame[], index: number): Line[] {
  const lines: Line[] = [];
  for (const f of frames.slice(0, index + 1)) {
    const d = f.event.data;
    switch (f.event.type) {
      case "user": lines.push({ kind: "customer", text: String(d.message), turn: f.turn }); break;
      case "reply": lines.push({ kind: "agent", text: String(d.reply), turn: null }); break;
      case "tool_call": lines.push({ kind: "tool", text: f.sentence, turn: null }); break;
      case "tool_result": { const last = [...lines].reverse().find((l) => l.kind === "tool" && l.answer === undefined); if (last) last.answer = f.sentence; break; }
      default: lines.push({ kind: "note", text: f.sentence, turn: null });
    }
  }
  return lines;
}
