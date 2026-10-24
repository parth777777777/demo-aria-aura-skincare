from pathlib import Path
from typing import Any

import pytest

from app.data import orders


@pytest.fixture(autouse=True)
def reset_order_cache() -> Any:
    orders._load_canonical_orders.cache_clear()
    yield
    orders._load_canonical_orders.cache_clear()


@pytest.mark.parametrize(
    ("order_id", "customer", "status"),
    [
        ("ORD-101", "Priya Sharma", "Out for Delivery"),
        ("ORD-102", "Rahul Verma", "Delivered"),
        ("ORD-103", "Ananya Patel", "Processing"),
    ],
)
def test_get_order_by_id_returns_documented_orders(
    order_id: str, customer: str, status: str
) -> None:
    result = orders.get_order_by_id(order_id)

    assert result is not None
    assert result["order_id"] == order_id
    assert result["customer"] == customer
    assert result["status"] == status


def test_id_normalizes_case_and_surrounding_whitespace() -> None:
    assert orders.get_order_by_id("  ord-101 \t")["order_id"] == "ORD-101"


def test_unknown_id_returns_none() -> None:
    assert orders.get_order_by_id("ORD-999") is None


def test_returned_order_is_deep_copy() -> None:
    first = orders.get_order_by_id("ORD-103")
    assert first is not None
    first["items"].append("Changed item")
    first["customer"] = "Changed customer"

    second = orders.get_order_by_id("ORD-103")
    assert second is not None
    assert second["items"] == ["Green Tea Face Wash", "Green Tea Toner"]
    assert second["customer"] == "Ananya Patel"


def test_canonical_json_is_read_once(monkeypatch: pytest.MonkeyPatch) -> None:
    real_open = Path.open
    opened: list[Path] = []

    def counted_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == orders.ORDERS_FILE:
            opened.append(path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counted_open)
    orders.get_order_by_id("ORD-101")
    orders.get_order_by_id("ORD-102")
    orders.get_order_by_id("ORD-103")

    assert len(opened) == 1


@pytest.mark.parametrize(
    ("contents", "message"),
    [("{broken", "invalid JSON"), (None, "not found")],
)
def test_data_load_failures_raise_clear_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contents: str | None,
    message: str,
) -> None:
    data_file = tmp_path / "orders.json"
    if contents is not None:
        data_file.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(orders, "ORDERS_FILE", data_file)

    with pytest.raises(orders.OrderDataError, match=message):
        orders.get_order_by_id("ORD-999")


@pytest.mark.parametrize(
    ("value", "error", "message"),
    [(None, TypeError, "string"), (" \t", ValueError, "empty")],
)
def test_invalid_order_ids_raise_documented_errors(
    value: object, error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        orders.get_order_by_id(value)  # type: ignore[arg-type]
