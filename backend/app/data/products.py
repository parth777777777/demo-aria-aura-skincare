"""Read-only access to the canonical demo product catalog."""

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

PRODUCTS_FILE = Path(__file__).resolve().with_name("products.json")


class ProductDataError(ValueError):
    """Raised when the product catalog is missing or malformed."""


@lru_cache(maxsize=1)
def _load() -> dict[str, dict[str, Any]]:
    try:
        with PRODUCTS_FILE.open(encoding="utf-8") as file:
            records = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise ProductDataError("Could not load product catalog.") from error
    if not isinstance(records, list):
        raise ProductDataError("Product catalog must be a JSON array.")
    products: dict[str, dict[str, Any]] = {}
    for record in records:
        if (not isinstance(record, dict) or set(record) != {"id", "name", "price_inr"}
                or not isinstance(record["id"], str) or not record["id"].strip()
                or not isinstance(record["name"], str) or not record["name"].strip()
                or isinstance(record["price_inr"], bool)
                or not isinstance(record["price_inr"], int) or record["price_inr"] < 0):
            raise ProductDataError("Product record has invalid fields.")
        if record["id"] in products:
            raise ProductDataError("Product IDs must be unique.")
        products[record["id"]] = record
    return products


def get_products() -> dict[str, dict[str, Any]]:
    return deepcopy(_load())
