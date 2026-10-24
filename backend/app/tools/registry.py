"""Strict, SDK-independent allowlist for Gemini-callable business tools."""

from collections.abc import Mapping
from copy import deepcopy
import math
from typing import Any

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

def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}

_DEFINITIONS = (
    {"name": "get_order_details", "description": "Look up current order details.",
     "parameters": _schema({"order_id": _ID}, ["order_id"])},
    {"name": "cancel_order", "description": "Cancel a Processing mock order in this session.",
     "parameters": _schema({"order_id": _ID}, ["order_id"])},
    {"name": "check_cancellation_eligibility", "description": "Check current cancellation eligibility.",
     "parameters": _schema({"order_id": _ID}, ["order_id"])},
    {"name": "check_return_eligibility", "description": "Check return eligibility using optional customer-declared product facts.",
     "parameters": _schema({"order_id": _ID, "customer_declared": _DECLARED_RETURN}, ["order_id"])},
    {"name": "check_damaged_product_eligibility", "description": "Check a damage claim using optional customer-declared report facts.",
     "parameters": _schema({"order_id": _ID, "customer_declared": _DECLARED_DAMAGE}, ["order_id"])},
)

_SUPPORTED = {definition["name"] for definition in _DEFINITIONS}

def _validate(name: str, arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, Mapping):
        raise ToolArgumentError("Arguments must be a JSON object.")
    allowed = {"order_id"}
    if name in {"check_return_eligibility", "check_damaged_product_eligibility"}:
        allowed.add("customer_declared")
    extra = set(arguments) - allowed
    if extra:
        raise ToolArgumentError("Unexpected argument(s): " + ", ".join(sorted(map(str, extra))) + ".")
    if "order_id" not in arguments:
        raise ToolArgumentError("Missing required argument: order_id.")
    order_id = arguments["order_id"]
    if not isinstance(order_id, str) or not order_id.strip() or len(order_id) > 32:
        raise ToolArgumentError("order_id must be a non-empty string.")
    validated: dict[str, Any] = {"order_id": order_id.strip().upper()}
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

def get_tool_definitions() -> list[dict[str, Any]]:
    return deepcopy(list(_DEFINITIONS))

def list_tools() -> tuple[str, ...]:
    return tuple(definition["name"] for definition in _DEFINITIONS)

def execute_tool(service: OrderService, name: str, arguments: Any) -> dict[str, Any]:
    if not isinstance(name, str) or name not in _SUPPORTED:
        return {"ok": False, "error": {"code": "UNKNOWN_TOOL", "message": "Tool is not available."}}
    try:
        validated = _validate(name, arguments)
    except ToolArgumentError as error:
        return {"ok": False, "error": {"code": "INVALID_ARGUMENTS", "message": str(error)}}
    return getattr(service, name)(**validated)
