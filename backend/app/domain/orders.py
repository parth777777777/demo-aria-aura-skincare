"""Trusted order lookup, policy checks, and session-local actions."""

import re
from copy import deepcopy
from threading import RLock
from typing import Any

from app.data.orders import get_order_by_id
from app.domain import policy

_ORDER_ID = re.compile(r"ORD-\d{3}", re.IGNORECASE)


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


class OrderService:
    """Overlay mutable order status over immutable canonical seed records."""

    def __init__(self) -> None:
        self._statuses: dict[str, str] = {}
        self._lock = RLock()

    def _current_order(self, order_id: str) -> tuple[str | None, dict[str, Any] | None]:
        if not isinstance(order_id, str) or not _ORDER_ID.fullmatch(order_id.strip()):
            return None, None
        normalized = order_id.strip().upper()
        order = get_order_by_id(normalized)
        if order is None:
            return normalized, None
        with self._lock:
            order["status"] = self._statuses.get(normalized, order["status"])
        return normalized, order

    def get_order_details(self, order_id: str) -> dict[str, Any]:
        normalized, order = self._current_order(order_id)
        if normalized is None:
            return _error("INVALID_ID", "Order ID must match ORD-###.")
        if order is None:
            return _error("NOT_FOUND", "No order was found for that ID.")
        total = order["total_inr"]
        fee = policy.shipping_fee(total)
        policies = {
            "cancellation_eligible": policy.cancellation_eligibility(order["status"]),
            "return_eligible": None,
            "damage_report_eligible": None,
            "cod_eligible": policy.cod_allowed(total),
            "shipping_fee_inr": fee,
            "standard_delivery": policy.delivery_estimate(),
        }
        if "delivered_days_ago" in order and order["delivered_days_ago"] > 7:
            # A known elapsed period beyond the window is sufficient to deny;
            # product-condition facts are intentionally not fabricated.
            policies["return_eligible"] = False
        return {"ok": True, "order": deepcopy(order), "policies": policies}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        normalized, order = self._current_order(order_id)
        if normalized is None:
            return _error("INVALID_ID", "Order ID must match ORD-###.")
        if order is None:
            return _error("NOT_FOUND", "No order was found for that ID.")
        with self._lock:
            current_status = self._statuses.get(normalized, order["status"])
            if not policy.cancellation_eligibility(current_status):
                code = "ALREADY_CANCELLED" if current_status == "Cancelled" else "NOT_ELIGIBLE"
                return _error(code, "Only orders currently in Processing can be cancelled.")
            self._statuses[normalized] = "Cancelled"
        return {"ok": True, "order_id": normalized, "status": "Cancelled"}

    def check_cancellation_eligibility(self, order_id: str) -> dict[str, Any]:
        result = self.get_order_details(order_id)
        if not result["ok"]:
            return result
        eligible = result["policies"]["cancellation_eligible"]
        return {"ok": True, "eligible": eligible,
                "reason": "ELIGIBLE" if eligible else "ORDER_NOT_PROCESSING"}

    def check_return_eligibility(
        self, order_id: str, customer_declared: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        result = self.get_order_details(order_id)
        if not result["ok"]:
            return result
        order = result["order"]
        declared = customer_declared or {}
        if order["status"].casefold() != "delivered" or order.get("delivered_days_ago", 0) > 7:
            return {"ok": True, "eligible": False, "reason": "POLICY_NOT_MET"}
        needed = [key for key in ("unopened", "unused", "original_packaging")
                  if key not in declared]
        if "delivered_days_ago" not in order:
            needed.append("delivery_age")
        if needed:
            return {"ok": True, "eligible": None,
                    "reason": "NEEDS_CUSTOMER_CONFIRMATION", "needed": needed}
        eligible = policy.return_eligibility(
            order, unopened=declared["unopened"], unused=declared["unused"],
            original_packaging=declared["original_packaging"])
        return {"ok": True, "eligible": eligible,
                "reason": "ELIGIBLE" if eligible else "POLICY_NOT_MET"}

    def check_damaged_product_eligibility(
        self, order_id: str, customer_declared: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        result = self.get_order_details(order_id)
        if not result["ok"]:
            return result
        declared = customer_declared or {}
        if result["order"]["status"].casefold() != "delivered":
            return {"ok": True, "eligible": False, "reason": "POLICY_NOT_MET"}
        needed = [key for key in ("hours_since_delivery", "has_photos") if key not in declared]
        if needed:
            return {"ok": True, "eligible": None,
                    "reason": "NEEDS_CUSTOMER_CONFIRMATION", "needed": needed}
        eligible = policy.damage_report_eligibility(
            result["order"], elapsed_hours=declared["hours_since_delivery"],
            photos_provided=declared["has_photos"])
        return {"ok": True, "eligible": eligible,
                "reason": "ELIGIBLE" if eligible else "POLICY_NOT_MET"}
