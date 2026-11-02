import { z } from "zod";
import { defineAgent, noCardNumbers, tool } from "../../src/core/index.js";
import type { Guardrail } from "../../src/core/index.js";

export const ORDERS: Record<string, { id: string; status: string; total: number; item: string }> = {
  "1042": { id: "1042", status: "delivered", total: 60, item: "Trail shoes" },
  "2077": { id: "2077", status: "delivered", total: 240, item: "Rain jacket" },
  "3150": { id: "3150", status: "in_transit", total: 35, item: "Socks" },
};

export const REFUND_APPROVAL_LIMIT = 100;

const lookupOrder = tool({
  name: "lookup_order",
  description: "Look up an order by its id. Returns status, total and item.",
  input: z.object({ orderId: z.string() }),
  run: ({ orderId }) => ORDERS[orderId] ?? { error: "Order not found" },
});

const issueRefund = tool({
  name: "issue_refund",
  description: "Refund an order that has been delivered. Amount must not exceed the order total.",
  input: z.object({ orderId: z.string(), amount: z.number().positive() }),
  requiresApproval: ({ amount }) => (amount > REFUND_APPROVAL_LIMIT ? `Refund over ${REFUND_APPROVAL_LIMIT} needs approval` : false),
  run: ({ orderId, amount }) => {
    const order = ORDERS[orderId];
    if (!order) throw new Error("Order not found");
    if (order.status !== "delivered") throw new Error("Only delivered orders can be refunded");
    if (amount > order.total) throw new Error("Amount exceeds order total");
    return { orderId, refunded: amount };
  },
});

export const supportAgent = (extraGuardrails: Guardrail[] = []) =>
  defineAgent({
    id: "support",
    instructions: [
      "You are a customer support agent for an online store.",
      "Be concise and friendly. Use tools to check facts before answering; never guess order details.",
      `Refunds above ${REFUND_APPROVAL_LIMIT} require human approval, which the system handles.`,
      "Never reveal payment card numbers. If you cannot help, hand off to a human.",
    ].join("\n"),
    tools: [lookupOrder, issueRefund],
    guardrails: [noCardNumbers(), ...extraGuardrails],
  });
