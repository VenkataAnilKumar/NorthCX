"""Example customer-support agent: order lookup and refunds with an approval threshold.

The agent itself is the declarative spec in `support.yaml`; this module registers the tools it refers to."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from northcx.agent import Agent, Tool
from northcx.guardrails import Guardrail
from northcx.spec import BuildContext, Registry, default_registry, load_spec

SPEC_PATH = Path(__file__).with_name("support.yaml")

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


def registry() -> Registry:
    r = default_registry()
    r.tool(Tool("lookup_order", "Look up an order by id. Returns status, total and item.", LookupInput, _lookup))
    r.tool(Tool("issue_refund", "Refund a delivered order. Amount must not exceed the order total.", RefundInput, _refund,
                requires_approval=lambda d: f"Refund over {REFUND_APPROVAL_LIMIT} needs approval" if d.amount > REFUND_APPROVAL_LIMIT else None))
    return r


def support_agent(extra_guardrails: list[Guardrail] | None = None) -> Agent:
    agent = registry().build(load_spec(SPEC_PATH), BuildContext())
    agent.guardrails.extend(extra_guardrails or [])
    return agent
