"""Offline demo model: a few keyword rules so the platform can be tried without an API key.
It is not an AI model. Use AnthropicLLM for real conversations."""
from __future__ import annotations

import json
import re
import uuid

from .llm import text, tool_call
from .types import LLMRequest, LLMResponse


def _last_user_text(req: LLMRequest) -> str:
    for m in reversed(req.messages):
        if m["role"] == "user" and isinstance(m["content"], str) and not m["content"].startswith("[supervisor]"):
            return m["content"]
    return ""


def _last_tool_result(req: LLMRequest) -> dict | None:
    last = req.messages[-1]
    if last["role"] == "user" and isinstance(last["content"], list):
        for b in last["content"]:
            if b.get("type") == "tool_result":
                return b
    return None


class DemoLLM:
    async def complete(self, req: LLMRequest) -> LLMResponse:
        result = _last_tool_result(req)
        if result is not None:
            if result.get("is_error"):
                return text(f"I couldn't complete that: {result['content']}")
            data = json.loads(result["content"]) if result["content"].startswith("{") else {}
            if "refunded" in data:
                return text(f"Done. I refunded {data['refunded']} for order {data['order_id']}.")
            if "status" in data:
                return text(f"Order {data['id']} ({data['item']}) is {data['status']}; total {data['total']}.")
            return text("Sorry, I couldn't find that order.")
        msg = _last_user_text(req)
        low = msg.lower()
        if msg.startswith("[system]"):  # platform notice, for example an approval outcome
            if "declined" in low:
                return text("A teammate reviewed your request and couldn't approve it. Would you like to speak with a person?")
            if '"error"' in low:
                return text("I'm sorry, the approved action could not be completed. A teammate will follow up.")
            amount = re.search(r'"refunded": ([\d.]+)', msg)
            return text(f"Good news: your refund of {amount.group(1)} was approved and processed." if amount
                        else "Your request was approved and completed.")
        order = re.search(r"\b(\d{4})\b", msg)
        if re.search(r"\b(human|person|agent|someone)\b", low):
            return tool_call("handoff_to_human", {"reason": "Customer asked for a person"}, f"tu_{uuid.uuid4().hex[:6]}")
        if "refund" in low and order:
            amount = re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", msg.replace(order.group(1), "", 1))
            return tool_call("issue_refund", {"order_id": order.group(1), "amount": float(amount.group(1)) if amount else 60.0})
        if order:
            return tool_call("lookup_order", {"order_id": order.group(1)})
        return text("Hi! I can look up an order (try 'where is order 1042?') or issue a refund (try 'refund 60 for order 1042').")
