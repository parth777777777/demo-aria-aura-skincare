"""Deterministic, validated v1 call summaries; replaceable via SummaryGenerator."""

from typing import Any, Protocol

INTENTS = {"order_status", "cancellation", "return", "damaged_product",
           "delivery_info", "place_order", "policy_question", "out_of_scope", "unclear"}
RESOLUTIONS = {"resolved", "not_eligible", "unresolved", "out_of_scope", "no_interaction"}


class SummaryGenerator(Protocol):
    def generate(self, tools: list[dict[str, Any]], transcript: list[dict[str, Any]]) -> dict[str, Any]: ...


def validate_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"customer_intent", "order_id", "resolution_status", "call_summary"}:
        raise ValueError("Summary must contain exactly the four contract fields.")
    if value["customer_intent"] not in INTENTS or value["resolution_status"] not in RESOLUTIONS:
        raise ValueError("Summary contains an unsupported enum value.")
    if value["order_id"] is not None and (not isinstance(value["order_id"], str) or not value["order_id"].startswith("ORD-")):
        raise ValueError("Summary order_id must be null or an order ID.")
    if not isinstance(value["call_summary"], str) or not value["call_summary"].strip() or len(value["call_summary"]) > 1000:
        raise ValueError("Summary call_summary must be non-empty and at most 1000 characters.")
    return value


class DeterministicSummary:
    @staticmethod
    def _highlights(tools: list[dict[str, Any]]) -> list[str]:
        highlights: list[str] = []
        for item in tools:
            name, result = item["name"], item["result"]
            if not result.get("ok"):
                continue

            order = result.get("order")
            order_id = item.get("order_id") or result.get("order_id")
            if isinstance(order, dict):
                order_id = order.get("order_id") or order_id

            if name == "place_order":
                if order_id:
                    highlight = f"Placed order {order_id}."
                else:
                    continue
            elif name == "get_order_details":
                if not order_id:
                    continue
                status = order.get("status") if isinstance(order, dict) else None
                detail = f" (status: {status})" if isinstance(status, str) and status else ""
                highlight = f"Viewed order {order_id}{detail}."
                # Avoid repetition when consecutive identical lookup results occur.
                if highlights and highlights[-1] == highlight:
                    continue
            elif name == "cancel_order":
                if not order_id:
                    continue
                status = result.get("status")
                if status == "Cancelled":
                    highlight = f"Cancelled order {order_id}."
                else:
                    continue
            else:
                continue

            highlights.append(highlight)
        return highlights

    def generate(self, tools: list[dict[str, Any]], transcript: list[dict[str, Any]]) -> dict[str, Any]:
        latest_order = next((item.get("order_id") for item in reversed(tools)
                             if item.get("result", {}).get("ok") and item.get("order_id")), None)
        intent = "unclear"
        resolution = "no_interaction" if not transcript and not tools else "unresolved"
        for item in tools:
            name, result = item["name"], item["result"]
            if name.startswith("check_return"):
                intent = "return"
            elif name.startswith("check_damaged"):
                intent = "damaged_product"
            elif name in {"cancel_order", "check_cancellation_eligibility"}:
                intent = "cancellation"
            elif name in {"get_order_details"}:
                intent = "order_status"
            elif name in {"build_order_cart", "place_order"}:
                intent = "place_order"
            if result.get("ok"):
                if result.get("eligible") is False:
                    resolution = "not_eligible"
                elif result.get("eligible") is None:
                    resolution = "unresolved"
                else:
                    resolution = "resolved"
            elif result.get("error", {}).get("code") not in {"CONFIRMATION_REQUIRED"}:
                resolution = "unresolved"
        if not tools and transcript:
            text = " ".join(part["text"] for part in transcript).casefold()
            if any(word in text for word in ("flight", "booking", "unrelated")):
                intent, resolution = "out_of_scope", "out_of_scope"
            elif any(word in text for word in ("cancel", "cancellation")):
                intent = "cancellation"
            elif any(word in text for word in ("return", "refund")):
                intent = "return"
            elif any(word in text for word in ("delivery", "shipping")):
                intent = "delivery_info"
            else:
                intent, resolution = "policy_question", "unresolved"
        highlights = self._highlights(tools)
        text = " ".join(highlights) if highlights else f"Call ended with {resolution.replace('_', ' ')}."
        return validate_summary({"customer_intent": intent, "order_id": latest_order,
                                 "resolution_status": resolution, "call_summary": text})
