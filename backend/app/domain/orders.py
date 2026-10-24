"""Trusted order lookup, policy checks, and session-local actions."""

import re
from copy import deepcopy
from threading import RLock
from typing import Any

from app.data.orders import get_order_by_id
from app.data.products import get_products
from app.domain import policy

_ORDER_ID = re.compile(r"ORD-\d{3}", re.IGNORECASE)


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


class OrderService:
    """Overlay mutable order status over immutable canonical seed records."""

    def __init__(self) -> None:
        self._statuses: dict[str, str] = {}
        self._new_orders: dict[str, dict[str, Any]] = {}
        self._carts: dict[str, dict[str, Any]] = {}
        self._placed_carts: dict[str, str] = {}
        self._next_order_number = 201
        self._lock = RLock()

    def _current_order(self, order_id: str) -> tuple[str | None, dict[str, Any] | None]:
        if not isinstance(order_id, str) or not _ORDER_ID.fullmatch(order_id.strip()):
            return None, None
        normalized = order_id.strip().upper()
        with self._lock:
            order = deepcopy(self._new_orders.get(normalized))
        if order is None:
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
                message = "Only orders currently in Processing can be cancelled. Shipped or out-for-delivery orders may be refused at the doorstep."
                return _error(code, message)
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
        if order["status"].casefold() != "delivered":
            return {"ok": True, "eligible": False, "reason": "NOT_DELIVERED"}
        if order.get("delivered_days_ago", 0) > 7:
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
            return {"ok": True, "eligible": False, "reason": "NOT_DELIVERED"}
        order = result["order"]
        known_hours = order.get("delivered_days_ago")
        known_hours = known_hours * 24 if known_hours is not None else None
        needed = ["has_photos"] if "has_photos" not in declared else []
        if known_hours is None and "hours_since_delivery" not in declared:
            needed.append("hours_since_delivery")
        if needed:
            return {"ok": True, "eligible": None,
                    "reason": "NEEDS_CUSTOMER_CONFIRMATION", "needed": needed}
        eligible = policy.damage_report_eligibility(
            order, elapsed_hours=(known_hours if known_hours is not None
                                  else declared["hours_since_delivery"]),
            photos_provided=declared["has_photos"])
        return {"ok": True, "eligible": eligible,
                "reason": "ELIGIBLE" if eligible else "POLICY_NOT_MET"}

    def build_order_cart(self, items: list[dict[str, Any]], payment_method: str) -> dict[str, Any]:
        products = get_products()
        cart_items = []
        subtotal = 0
        for item in items:
            product = products.get(item["product_id"])
            if product is None:
                return _error("PRODUCT_NOT_FOUND", "A cart item is not in the demo catalog.")
            line_total = product["price_inr"] * item["quantity"]
            subtotal += line_total
            cart_items.append({"product_id": product["id"], "name": product["name"],
                               "quantity": item["quantity"], "unit_price_inr": product["price_inr"],
                               "line_total_inr": line_total})
        shipping = policy.shipping_fee(subtotal)
        total = subtotal + shipping
        cart = {"items": cart_items, "payment_method": payment_method,
                "subtotal_inr": subtotal, "shipping_fee_inr": shipping,
                "total_inr": total, "cod_allowed": policy.cod_allowed(total)}
        with self._lock:
            cart_id = f"CART-{len(self._carts) + 1:06d}"
            cart["cart_id"] = cart_id
            self._carts[cart_id] = cart
        return {"ok": True, "cart": deepcopy(cart)}

    def place_order(self, cart_id: str) -> dict[str, Any]:
        with self._lock:
            cart = self._carts.get(cart_id)
            if cart is None:
                return _error("CART_NOT_FOUND", "No cart was found in this session.")
            if cart_id in self._placed_carts:
                existing = self._new_orders[self._placed_carts[cart_id]]
                return {"ok": True, "order": deepcopy(existing), "idempotent": True}
            if cart["payment_method"] == "COD" and not policy.cod_allowed(cart["total_inr"]):
                return _error("COD_NOT_ALLOWED", "Cash on delivery is unavailable for totals above ₹2,500.")
            order_id = f"ORD-{self._next_order_number:03d}"
            self._next_order_number += 1
            order = {"order_id": order_id, "customer": "Demo Customer",
                     "items": [item["name"] for item in cart["items"]],
                     "total_inr": cart["total_inr"], "status": "Processing",
                     "carrier": "Not yet assigned", "tracking_number": "Not yet assigned",
                     "payment_method": cart["payment_method"], "cart_id": cart_id}
            self._new_orders[order_id] = order
            self._placed_carts[cart_id] = order_id
            return {"ok": True, "order": deepcopy(order), "idempotent": False}
