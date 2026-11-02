import { z } from "zod";
import type { Guardrail } from "./guardrails.js";
import type { MemoryStore } from "./store.js";
import type { ToolSpec } from "./types.js";

export interface ToolContext {
  sessionId: string;
  customerId?: string;
  memory: MemoryStore;
}

export interface ToolDef<S extends z.ZodType = z.ZodType> {
  name: string;
  description: string;
  input: S;
  run(input: z.infer<S>, ctx: ToolContext): Promise<unknown> | unknown;
  /** Return a reason string to pause for human approval instead of executing. */
  requiresApproval?(input: z.infer<S>): string | false;
}

export const tool = <S extends z.ZodType>(def: ToolDef<S>) => def;

export interface AgentDef {
  id: string;
  /** Goals and guardrails in natural language, not a flowchart. */
  instructions: string;
  tools: ToolDef<any>[];
  model?: string;
  guardrails?: Guardrail[];
  maxSteps?: number;
}

export const defineAgent = (def: AgentDef): Required<AgentDef> => ({
  model: "",
  guardrails: [],
  maxSteps: 8,
  ...def,
}) as Required<AgentDef>;

export function toolSpec(t: ToolDef<any>): ToolSpec {
  const schema = z.toJSONSchema(t.input) as Record<string, unknown>;
  delete schema.$schema;
  return { name: t.name, description: t.description, input_schema: schema };
}
