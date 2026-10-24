"""Data access for the canonical mock orders."""

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any


ORDERS_FILE = Path(__file__).resolve().with_name("orders.json")
_REQUIRED_FIELDS = {
    "order_id",
    "customer",
    "items",
    "total_inr",
    "status",
    "carrier",
    "tracking_number",
}


class OrderDataError(ValueError):
    """Raised when canonical order data cannot be loaded or validated."""


def _read_orders(path: Path) -> dict[str, dict[str, Any]]:
    try:
        with path.open(encoding="utf-8") as orders_file:
            records = json.load(orders_file)
    except FileNotFoundError as error:
        raise OrderDataError(f"Order data file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise OrderDataError(
            f"Order data file contains invalid JSON at line {error.lineno}, "
            f"column {error.colno}: {path}"
        ) from error
    except OSError as error:
        raise OrderDataError(f"Could not read order data file {path}: {error}") from error

    if not isinstance(records, list):
        raise OrderDataError("Order data must be a JSON array")

    orders: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        prefix = f"Order record at index {index}"
        if not isinstance(record, dict):
            raise OrderDataError(f"{prefix} must be a JSON object")
        missing = _REQUIRED_FIELDS - record.keys()
        if missing:
            raise OrderDataError(f"{prefix} is missing fields: {', '.join(sorted(missing))}")
        order_id = record["order_id"]
        if not isinstance(order_id, str) or not order_id.strip():
            raise OrderDataError(f"{prefix} has an invalid order_id")
        if order_id in orders:
            raise OrderDataError(f"Duplicate order_id in order data: {order_id}")
        if not isinstance(record["customer"], str) or not isinstance(record["status"], str):
            raise OrderDataError(f"{prefix} customer and status must be strings")
        if not isinstance(record["items"], list) or not all(
            isinstance(item, str) for item in record["items"]
        ):
            raise OrderDataError(f"{prefix} items must be an array of strings")
        if isinstance(record["total_inr"], bool) or not isinstance(
            record["total_inr"], (int, float)
        ):
            raise OrderDataError(f"{prefix} total_inr must be a number")
        orders[order_id] = record

    return orders


@lru_cache(maxsize=1)
def _load_canonical_orders() -> dict[str, dict[str, Any]]:
    """Load the canonical JSON once; cached data stays private to this module."""
    return _read_orders(ORDERS_FILE)


def load_orders(path: Path = ORDERS_FILE) -> dict[str, dict[str, Any]]:
    """Load orders, sharing the canonical cache or reading a custom path."""
    if path == ORDERS_FILE:
        return _load_canonical_orders()
    return _read_orders(path)


def get_order_by_id(order_id: str) -> dict[str, Any] | None:
    """Return a deep-copied order; blank/non-string IDs are invalid.

    A non-string ID raises TypeError, and an empty ID after trimming raises
    ValueError. Data-file failures raise OrderDataError rather than looking
    like an unknown order.
    """
    if not isinstance(order_id, str):
        raise TypeError("order_id must be a string")
    normalized_id = order_id.strip().upper()
    if not normalized_id:
        raise ValueError("order_id must not be empty")

    order = _load_canonical_orders().get(normalized_id)
    return deepcopy(order) if order is not None else None


class OrderRepository:
    """Read-only repository over the canonical mock-order fixtures."""

    def __init__(self, path: Path = ORDERS_FILE) -> None:
        self._orders = load_orders(path)

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        return deepcopy(self._orders.get(order_id))
