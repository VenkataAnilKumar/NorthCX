import type { Message } from "./types.js";

/** Session + long-term memory. Swap for Postgres/Redis in production. */
export interface MemoryStore {
  loadMessages(sessionId: string): Promise<Message[]>;
  saveMessages(sessionId: string, messages: Message[]): Promise<void>;
  getFacts(customerId: string): Promise<Record<string, string>>;
  setFact(customerId: string, key: string, value: string): Promise<void>;
}

export class InMemoryStore implements MemoryStore {
  private msgs = new Map<string, Message[]>();
  private facts = new Map<string, Record<string, string>>();
  async loadMessages(id: string) { return structuredClone(this.msgs.get(id) ?? []); }
  async saveMessages(id: string, m: Message[]) { this.msgs.set(id, structuredClone(m)); }
  async getFacts(id: string) { return { ...(this.facts.get(id) ?? {}) }; }
  async setFact(id: string, k: string, v: string) { this.facts.set(id, { ...(this.facts.get(id) ?? {}), [k]: v }); }
}
