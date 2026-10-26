"""Trusted order lookup, policy checks, and session-local actions."""

import re
from copy import deepcopy
from threading import RLock
from typing import Any

from app.data.orders import get_order_by_id, load_orders
from app.data.products import get_products
from app.domain import policy

_ORDER_ID = re.compile(r"ORD-\d{3}", re.IGNORECASE)


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


class OrderService:
    """Overlay mutable order status over immutable canonical seed records."""

    def __init__(self, *, owned_orders: list[dict[str, Any]] | None = None,
                 owned_carts: list[dict[str, Any]] | None = None,
                 customer_name: str | None = None,
                 include_mock_fixtures: bool = True) -> None:
        self._statuses: dict[str, str] = {}
        self._new_orders: dict[str, dict[str, Any]] = {
            order["order_id"].upper(): deepcopy(order) for order in (owned_orders or [])
        }
        self._include_mock_fixtures = include_mock_fixtures
        self._customer_name = customer_name or "Demo Customer"
        self._carts: dict[str, dict[str, Any]] = {
            cart["cart_id"]: deepcopy(cart) for cart in (owned_carts or [])
        }
        self._placed_carts: dict[str, str] = {
            order["cart_id"]: order["order_id"].upper()
            for order in (owned_orders or []) if order.get("cart_id")
        }
        order_numbers = [
            int(match.group(1)) for order in (owned_orders or [])
            if (match := re.fullmatch(r"ORD-(\d+)", order.get("order_id", "").upper()))
        ]
        cart_numbers = [
            int(match.group(1)) for cart in (owned_carts or [])
            if (match := re.fullmatch(r"CART-(\d+)", cart.get("cart_id", "")))
        ]
        self._next_order_number = max([200, *order_numbers]) + 1
        self._next_cart_number = max([0, *cart_numbers]) + 1
        self._lock = RLock()

    def _current_order(self, order_id: str) -> tuple[str | None, dict[str, Any] | None]:
        if not isinstance(order_id, str) or not _ORDER_ID.fullmatch(order_id.strip()):
            return None, None
        normalized = order_id.strip().upper()
        with self._lock:
            order = deepcopy(self._new_orders.get(normalized))
        if order is None and self._include_mock_fixtures:
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

    def list_orders(self) -> list[dict[str, Any]]:
        """List the current call's complete mock dataset, including sample fixtures."""
        with self._lock:
            statuses = dict(self._statuses)
            new_orders = deepcopy(self._new_orders)
        orders = deepcopy(load_orders()) if self._include_mock_fixtures else {}
        orders.update(new_orders)
        for order_id, order in orders.items():
            order["status"] = statuses.get(order_id, order["status"])
        return [deepcopy(orders[order_id]) for order_id in sorted(orders)]

    def owned_orders(self) -> list[dict[str, Any]]:
        """Return this service's mutable order state, without global fixtures."""
        with self._lock:
            orders = deepcopy(self._new_orders)
            for order_id, order in orders.items():
                order["status"] = self._statuses.get(order_id, order["status"])
            return [orders[order_id] for order_id in sorted(orders)]

    def owned_carts(self) -> list[dict[str, Any]]:
        """Return temporary carts for persistence in their owning demo identity."""
        with self._lock:
            return [deepcopy(self._carts[cart_id]) for cart_id in sorted(self._carts)]

    def list_carts(self) -> list[dict[str, Any]]:
        """List this service's carts and whether each can currently be placed."""
        carts = self.owned_carts()
        with self._lock:
            placed = set(self._placed_carts)
        for cart in carts:
            if cart["cart_id"] in placed:
                cart["placement_status"] = "placed"
            else:
                price_error = self._cart_current_price_error(cart)
                if price_error is None:
                    integrity_error = self._cart_integrity_error(cart)
                    price_error = integrity_error
                cart["placement_status"] = (
                    "ready" if price_error is None
                    else "price_changed" if price_error["error"]["code"] == "CART_PRICE_CHANGED"
                    else "unavailable"
                )
        return carts

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
        normalized_products: dict[str, set[str]] = {}
        for product in products.values():
            for value in (product["id"], product["name"]):
                key = re.sub(r"[^a-z0-9]", "", value.casefold())
                normalized_products.setdefault(key, set()).add(product["id"])
        cart_items = []
        subtotal = 0
        for item in items:
            product_key = re.sub(r"[^a-z0-9]", "", item["product_id"].casefold())
            matches = normalized_products.get(product_key, set())
            if len(matches) > 1:
                return _error("AMBIGUOUS_PRODUCT", "Product name or ID matches multiple catalog products.")
            if not matches:
                return _error("PRODUCT_NOT_FOUND", "A cart item is not in the demo catalog.")
            product = products[next(iter(matches))]
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
            cart_id = f"CART-{self._next_cart_number:06d}"
            self._next_cart_number += 1
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
            price_error = self._cart_current_price_error(cart)
            if price_error is not None:
                return price_error
            integrity_error = self._cart_integrity_error(cart)
            if integrity_error is not None:
                return integrity_error
            if cart["payment_method"] == "COD" and not policy.cod_allowed(cart["total_inr"]):
                return _error("COD_NOT_ALLOWED", "Cash on delivery is unavailable for totals above ₹2,500.")
            order_id = f"ORD-{self._next_order_number:03d}"
            self._next_order_number += 1
            order = {"order_id": order_id, "customer": self._customer_name,
                     "items": [item["name"] for item in cart["items"]],
                     "total_inr": cart["total_inr"], "status": "Processing",
                     "carrier": "Not yet assigned", "tracking_number": "Not yet assigned",
                     "payment_method": cart["payment_method"], "cart_id": cart_id}
            self._new_orders[order_id] = order
            self._placed_carts[cart_id] = order_id
            return {"ok": True, "order": deepcopy(order), "idempotent": False}

    def get_placed_order(self, cart_id: str) -> dict[str, Any] | None:
        """Return an already-created order for this cart, if present."""
        with self._lock:
            order_id = self._placed_carts.get(cart_id)
            order = self._new_orders.get(order_id) if order_id is not None else None
            return deepcopy(order) if order is not None else None

    def get_cart_details(self, cart_id: str) -> dict[str, Any]:
        """Return a copy of a session cart for confirmation quoting/revalidation."""
        with self._lock:
            cart = deepcopy(self._carts.get(cart_id))
        if cart is None:
            return _error("CART_NOT_FOUND", "No cart was found in this session.")
        price_error = self._cart_current_price_error(cart)
        if price_error is not None:
            return price_error
        return {"ok": True, "cart": cart}

    @staticmethod
    def _cart_current_price_error(cart: dict[str, Any]) -> dict[str, Any] | None:
        products = get_products()
        for item in cart.get("items", []):
            product = products.get(item.get("product_id"))
            if product is None:
                return _error(
                    "PRODUCT_NOT_AVAILABLE",
                    "A cart product is no longer available. Build a new cart before placing an order.",
                )
            if product["price_inr"] != item.get("unit_price_inr"):
                return _error(
                    "CART_PRICE_CHANGED",
                    "A product price changed. Build a new cart and confirm its updated total before placing an order.",
                )
        return None

    @staticmethod
    def _cart_integrity_error(cart: dict[str, Any]) -> dict[str, Any] | None:
        products = get_products()
        subtotal = 0
        for item in cart.get("items", []):
            product = products.get(item.get("product_id"))
            if product is None:
                return _error("PRODUCT_NOT_AVAILABLE", "A cart product is no longer available.")
            line_total = product["price_inr"] * item.get("quantity", 0)
            if item.get("line_total_inr") != line_total:
                return _error("CART_DETAILS_CHANGED", "Cart details changed. Build a new cart.")
            subtotal += line_total
        expected_shipping = policy.shipping_fee(subtotal)
        expected_total = subtotal + expected_shipping
        if (cart.get("subtotal_inr") != subtotal
                or cart.get("shipping_fee_inr") != expected_shipping
                or cart.get("total_inr") != expected_total
                or cart.get("cod_allowed") != policy.cod_allowed(expected_total)):
            return _error(
                "CART_DETAILS_CHANGED",
                "Cart totals changed. Build a new cart before placing an order.",
            )
        return None
