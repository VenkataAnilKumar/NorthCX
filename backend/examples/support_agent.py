"""Example customer-support agent: order lookup and refunds with an approval threshold."""
from __future__ import annotations

from pydantic import BaseModel, Field

from northcx.agent import Agent, Tool
from northcx.guardrails import Guardrail, NoCardNumbers
from northcx.safety import PIIDetection, PromptInjection

ORDERS = {
    "1042": {"id": "1042", "status": "delivered", "total": 60, "item": "Trail shoes"},
    "2077": {"id": "2077", "status": "delivered", "total": 240, "item": "Rain jacket"},
    "3150": {"id": "3150", "status": "in_transit", "total": 35, "item": "Socks"},
}
REFUND_APPROVAL_LIMIT = 100


class LookupInput(BaseModel):
    order_id: str


class RefundInput(BaseModel):
    order_id: str
    amount: float = Field(gt=0)


def _lookup(data: LookupInput, ctx):
    return ORDERS.get(data.order_id, {"error": "Order not found"})


def _refund(data: RefundInput, ctx):
    order = ORDERS.get(data.order_id)
    if not order:
        raise ValueError("Order not found")
    if order["status"] != "delivered":
        raise ValueError("Only delivered orders can be refunded")
    if data.amount > order["total"]:
        raise ValueError("Amount exceeds order total")
    return {"order_id": data.order_id, "refunded": data.amount}


def support_agent(extra_guardrails: list[Guardrail] | None = None) -> Agent:
    return Agent(
        id="support",
        instructions="\n".join([
            "You are a customer support agent for an online store.",
            "Be concise and friendly. Use tools to check facts before answering; never guess order details.",
            f"Refunds above {REFUND_APPROVAL_LIMIT} require human approval, which the system handles.",
            "Never reveal payment card numbers. If you cannot help, hand off to a human.",
        ]),
        tools=[
            Tool("lookup_order", "Look up an order by id. Returns status, total and item.", LookupInput, _lookup),
            Tool("issue_refund", "Refund a delivered order. Amount must not exceed the order total.", RefundInput, _refund,
                 requires_approval=lambda d: f"Refund over {REFUND_APPROVAL_LIMIT} needs approval" if d.amount > REFUND_APPROVAL_LIMIT else None),
        ],
        guardrails=[NoCardNumbers(), *(extra_guardrails or [])],
        input_guardrails=[PIIDetection(mask_pii=True), PromptInjection()],
    )
