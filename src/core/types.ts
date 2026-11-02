export type TextBlock = { type: "text"; text: string };
export type ToolUseBlock = { type: "tool_use"; id: string; name: string; input: Record<string, unknown> };
export type ToolResultBlock = { type: "tool_result"; tool_use_id: string; content: string; is_error?: boolean };
export type Block = TextBlock | ToolUseBlock | ToolResultBlock;

export interface Message {
  role: "user" | "assistant";
  content: string | Block[];
}

export interface ToolSpec {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface LLMRequest {
  model?: string;
  system: string;
  messages: Message[];
  tools: ToolSpec[];
  maxTokens?: number;
}

export interface LLMResponse {
  content: Block[];
  stopReason: string;
}

/** Any model backend. The runtime only depends on this interface. */
export interface LLM {
  complete(req: LLMRequest): Promise<LLMResponse>;
}
