"""Strict, SDK-independent allowlist for Gemini-callable business tools."""

from collections.abc import Mapping
from copy import deepcopy
import math
from typing import Any

from app.data.products import get_products
from app.domain.confirmations import PendingActionStore
from app.domain.order_resolution import resolve_order_reference
from app.domain.orders import OrderService


class ToolArgumentError(ValueError):
    """Invalid model-supplied tool arguments."""


_ID = {"type": "string", "description": "Aura order ID (ORD-###)."}
_DECLARED_RETURN = {
    "type": "object", "properties": {key: {"type": "boolean"} for key in
        ("unopened", "unused", "original_packaging")}, "additionalProperties": False,
}
_DECLARED_DAMAGE = {"type": "object", "properties": {
    "hours_since_delivery": {"type": "number"}, "has_photos": {"type": "boolean"}
}, "additionalProperties": False}
_CART_ITEMS = {"type": "array", "minItems": 1, "maxItems": 10, "items": {
    "type": "object", "properties": {
        "product_id": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1, "maximum": 10}
    }, "required": ["product_id", "quantity"], "additionalProperties": False
}}

def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}

_DEFINITIONS = (
    {"name": "list_order_carts", "description": "List carts in the active authorized session. Account-mode carts may have been created during an earlier call; only place a cart marked ready after confirming its current details.",
     "parameters": _schema({}, [])},
    {"name": "list_orders", "description": "List every order in the active authorized data source. Mock DB results are the sample demo dataset, not the caller's personal orders.",
     "parameters": _schema({}, [])},
    {"name": "resolve_order_reference", "description": "Resolve a concise product or order reference such as 'vitamin C' against the active authorized orders. Use the result only when match_status is matched; ask the customer to clarify ambiguous or missing matches.",
     "parameters": _schema({"reference": {"type": "string", "description": "Product name, item phrase, order ID, or a contextual reference such as 'that one'."}}, ["reference"])},
    {"name": "get_order_details", "description": "Look up current order details.",
     "parameters": _schema({"order_id": _ID}, ["order_id"])},
    {"name": "cancel_order", "description": "Request cancellation of a Processing mock order. First call without confirmation_id stages the exact action; after the customer clearly confirms in the next turn, call again with the returned confirmation_id.",
     "parameters": _schema({"order_id": _ID, "confirmation_id": {"type": "string", "description": "One-time ID returned by the backend after asking for confirmation."}}, ["order_id"])},
    {"name": "check_cancellation_eligibility", "description": "Check current cancellation eligibility.",
     "parameters": _schema({"order_id": _ID}, ["order_id"])},
    {"name": "check_return_eligibility", "description": "Check return eligibility using optional customer-declared product facts.",
     "parameters": _schema({"order_id": _ID, "customer_declared": _DECLARED_RETURN}, ["order_id"])},
    {"name": "check_damaged_product_eligibility", "description": "Check a damage claim using optional customer-declared report facts.",
      "parameters": _schema({"order_id": _ID, "customer_declared": _DECLARED_DAMAGE}, ["order_id"])},
    {"name": "build_order_cart", "description": "Build and price a cart from the backend demo catalog.",
     "parameters": _schema({"items": _CART_ITEMS, "payment_method": {"type": "string", "enum": ["COD", "PREPAID"]}}, ["items", "payment_method"])},
    {"name": "place_order", "description": "Request placement of a cart belonging to this session. First call without confirmation_id stages the exact action; after the customer clearly confirms in the next turn, call again with the returned confirmation_id.",
     "parameters": _schema({"cart_id": {"type": "string"}, "confirmation_id": {"type": "string", "description": "One-time ID returned by the backend after asking for confirmation."}}, ["cart_id"])},
)

_SUPPORTED = {definition["name"] for definition in _DEFINITIONS}

def _validate(name: str, arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, Mapping):
        raise ToolArgumentError("Arguments must be a JSON object.")
    if name in {"list_orders", "list_order_carts"}:
        allowed = set()
    elif name == "resolve_order_reference":
        allowed = {"reference"}
    elif name == "build_order_cart":
        allowed = {"items", "payment_method"}
    elif name == "place_order":
        allowed = {"cart_id", "confirmation_id"}
    elif name == "cancel_order":
        allowed = {"order_id", "confirmation_id"}
    else:
        allowed = {"order_id"}
    if name in {"check_return_eligibility", "check_damaged_product_eligibility"}:
        allowed.add("customer_declared")
    extra = set(arguments) - allowed
    if extra:
        raise ToolArgumentError("Unexpected argument(s): " + ", ".join(sorted(map(str, extra))) + ".")
    if name == "build_order_cart":
        if set(arguments) != allowed:
            raise ToolArgumentError("items and payment_method are required.")
        items = arguments["items"]
        if not isinstance(items, list) or not 1 <= len(items) <= 10:
            raise ToolArgumentError("items must contain 1 to 10 distinct products.")
        cleaned = []
        seen = set()
        for item in items:
            if not isinstance(item, Mapping) or set(item) != {"product_id", "quantity"}:
                raise ToolArgumentError("Each item requires only product_id and quantity.")
            product_id, quantity = item["product_id"], item["quantity"]
            if not isinstance(product_id, str) or not product_id.strip():
                raise ToolArgumentError("product_id must be a non-empty string.")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 10:
                raise ToolArgumentError("quantity must be an integer from 1 to 10.")
            if product_id in seen:
                raise ToolArgumentError("Duplicate product IDs are not allowed.")
            seen.add(product_id)
            cleaned.append({"product_id": product_id, "quantity": quantity})
        method = arguments["payment_method"]
        if not isinstance(method, str) or method not in ("COD", "PREPAID"):
            raise ToolArgumentError("payment_method must be COD or PREPAID.")
        return {"items": cleaned, "payment_method": method}
    if name in {"list_orders", "list_order_carts"}:
        return {}
    if name == "resolve_order_reference":
        reference = arguments.get("reference")
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 120:
            raise ToolArgumentError("reference must be a non-empty string up to 120 characters.")
        return {"reference": reference.strip()}
    if name == "place_order":
        cart_id = arguments.get("cart_id")
        if not isinstance(cart_id, str) or not cart_id.strip() or len(cart_id) > 64:
            raise ToolArgumentError("cart_id must be a non-empty string.")
        validated = {"cart_id": cart_id.strip()}
        if "confirmation_id" in arguments:
            validated["confirmation_id"] = _confirmation_id(arguments["confirmation_id"])
        return validated
    if "order_id" not in arguments:
        raise ToolArgumentError("Missing required argument: order_id.")
    order_id = arguments["order_id"]
    if not isinstance(order_id, str) or not order_id.strip() or len(order_id) > 32:
        raise ToolArgumentError("order_id must be a non-empty string.")
    validated: dict[str, Any] = {"order_id": order_id.strip().upper()}
    if name == "cancel_order" and "confirmation_id" in arguments:
        validated["confirmation_id"] = _confirmation_id(arguments["confirmation_id"])
    if "customer_declared" in arguments:
        declared = arguments["customer_declared"]
        if not isinstance(declared, Mapping):
            raise ToolArgumentError("customer_declared must be an object.")
        keys = ({"unopened", "unused", "original_packaging"} if name == "check_return_eligibility"
                else {"hours_since_delivery", "has_photos"})
        if name not in {"check_return_eligibility", "check_damaged_product_eligibility"}:
            raise ToolArgumentError("customer_declared is not supported for this tool.")
        if set(declared) - keys:
            raise ToolArgumentError("Unexpected customer_declared field.")
        for key, value in declared.items():
            if key == "hours_since_delivery":
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) or value < 0):
                    raise ToolArgumentError("hours_since_delivery must be a finite non-negative number.")
            elif not isinstance(value, bool):
                raise ToolArgumentError(f"{key} must be a boolean.")
        validated["customer_declared"] = dict(declared)
    return validated


def _confirmation_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ToolArgumentError("confirmation_id must be a non-empty string.")
    return value.strip()

def get_tool_definitions() -> list[dict[str, Any]]:
    definitions = deepcopy(list(_DEFINITIONS))
    products = get_products()
    catalog = "; ".join(f"{product['id']} — {product['name']}"
                         for product in products.values())
    for definition in definitions:
        if definition["name"] == "build_order_cart":
            definition["description"] = (
                "Build and price a cart from the backend demo catalog. Valid product IDs and names: "
                f"{catalog}. Use the canonical ID or product name."
            )
    return definitions

def list_tools() -> tuple[str, ...]:
    return tuple(definition["name"] for definition in _DEFINITIONS)

def execute_tool(service: OrderService, name: str, arguments: Any, *,
                 confirmation_state: PendingActionStore | None = None,
                 finalized_user_turn: int = 0,
                 order_candidates: list[dict[str, Any]] | None = None,
                 order_source: str = "mock_db_sample_data",
                 conversation_context: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(name, str) or name not in _SUPPORTED:
        return {"ok": False, "error": {"code": "UNKNOWN_TOOL", "message": "Tool is not available."}}
    try:
        validated = _validate(name, arguments)
    except ToolArgumentError as error:
        return {"ok": False, "error": {"code": "INVALID_ARGUMENTS", "message": str(error)}}
    if name == "list_orders":
        orders = deepcopy(order_candidates if order_candidates is not None else service.list_orders())
        result: dict[str, Any] = {
            "ok": True,
            "source": order_source,
            "orders": orders,
        }
        if order_source == "mock_db_sample_data":
            result["notice"] = "These are sample demo orders and are not associated with a personal identity."
        return result
    if name == "list_order_carts":
        return {"ok": True, "carts": service.list_carts()}
    if name == "resolve_order_reference":
        candidates = order_candidates if order_candidates is not None else service.list_orders()
        result = resolve_order_reference(
            validated["reference"], candidates, conversation_context
        )
        if result.get("match_status") == "matched" and conversation_context is not None:
            conversation_context["last_order_id"] = result["order"]["order_id"]
        return result
    if name not in {"cancel_order", "place_order"}:
        result = getattr(service, name)(**validated)
        if name == "get_order_details" and result.get("ok") and conversation_context is not None:
            conversation_context["last_order_id"] = result["order"]["order_id"]
        return result

    state = confirmation_state if confirmation_state is not None else PendingActionStore()
    confirmation_id = validated.pop("confirmation_id", None)
    if confirmation_id is None:
        state.invalidate()
    if name == "cancel_order":
        order_result = service.get_order_details(validated["order_id"])
        if not order_result["ok"]:
            return order_result
        if confirmation_id is None and not order_result["policies"]["cancellation_eligible"]:
            return {"ok": False, "error": {
                "code": "NOT_ELIGIBLE",
                "message": "Only orders currently in Processing can be cancelled. Shipped or out-for-delivery orders may be refused at the doorstep.",
            }}
        order = order_result["order"]
        details = {
            "order_id": order["order_id"],
            "items": deepcopy(order.get("items", [])),
            "status": order["status"],
            "total_inr": order["total_inr"],
        }
    else:
        placed_order = service.get_placed_order(validated["cart_id"])
        if placed_order is not None:
            return {"ok": True, "order": placed_order, "idempotent": True}
        cart_result = service.get_cart_details(validated["cart_id"])
        if not cart_result["ok"]:
            return cart_result
        cart = cart_result["cart"]
        if confirmation_id is None and cart["payment_method"] == "COD" and not cart["cod_allowed"]:
            return {"ok": False, "error": {
                "code": "COD_NOT_ALLOWED",
                "message": "Cash on delivery is unavailable for totals above ₹2,500.",
            }}
        details = {
            "cart_id": cart["cart_id"],
            "items": deepcopy(cart["items"]),
            "subtotal_inr": cart["subtotal_inr"],
            "shipping_fee_inr": cart["shipping_fee_inr"],
            "total_inr": cart["total_inr"],
            "payment_method": cart["payment_method"],
        }

    if confirmation_id is None:
        pending = state.create(
            action=name, target=validated, details=details,
            user_turn=finalized_user_turn,
        )
        if name == "cancel_order":
            target_description = f"cancel order {validated['order_id']}"
        else:
            target_description = (
                f"place cart {validated['cart_id']} for ₹{details['total_inr']}"
            )
        return {
            "ok": False,
            "error": {
                "code": "CONFIRMATION_REQUIRED",
                "message": f"This action was not executed. Ask the customer to confirm that they want to {target_description}.",
            },
            "confirmation": {
                "confirmation_id": pending["confirmation_id"],
                "action": name,
                "target": deepcopy(validated),
                "details": details,
                "expires_in_seconds": state.ttl_seconds,
            },
        }

    pending, error_code = state.consume(
        confirmation_id=confirmation_id,
        action=name,
        target=validated,
        details=details,
        user_turn=finalized_user_turn,
    )
    if error_code:
        messages = {
            "CONFIRMATION_INVALID": "No matching pending action was found. Ask again before retrying.",
            "CONFIRMATION_EXPIRED": "That confirmation expired. Ask the customer to confirm the action again.",
            "CONFIRMATION_MISMATCH": "The pending confirmation does not match this action or target.",
            "CONFIRMATION_CHANGED": "The order or cart details changed. Present the updated details and ask again.",
            "CONFIRMATION_NOT_READY": "Wait for a new customer turn before confirming this action.",
            "CONFIRMATION_STALE": "The confirmation did not follow the action prompt. Ask again before retrying.",
        }
        return {"ok": False, "error": {"code": error_code, "message": messages[error_code]}}

    # A single-use confirmation is consumed before the business operation;
    # the service then rechecks current order status or cart policy.
    return getattr(service, name)(**pending["target"])
