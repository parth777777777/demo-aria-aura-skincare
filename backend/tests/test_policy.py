from copy import deepcopy
from decimal import Decimal

import pytest

from app.domain.policy import (
    PolicyInputError,
    cancellation_eligibility,
    cod_allowed,
    damage_report_eligibility,
    delivery_estimate,
    return_eligibility,
    shipping_fee,
)


@pytest.mark.parametrize(("amount", "expected_fee"), [(498, 50), (499, 50), (500, 0)])
def test_shipping_fee_boundary(amount: int, expected_fee: int) -> None:
    assert shipping_fee(amount) == expected_fee


@pytest.mark.parametrize("amount", [0, 499, 2500, Decimal("2500.00")])
def test_cod_allowed_inclusive_limit(amount: int | Decimal) -> None:
    assert cod_allowed(amount) is True


@pytest.mark.parametrize("amount", [2501, 3000])
def test_cod_not_allowed_above_limit(amount: int | float) -> None:
    assert cod_allowed(amount) is False


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("Processing", True),
        (" processing ", True),
        ("Out for Delivery", False),
        ("Delivered", False),
        ("Shipped", False),
        ("Unknown status", False),
    ],
)
def test_cancellation_eligibility(status: str, expected: bool) -> None:
    assert cancellation_eligibility(status) is expected


def _return_order(status: str = "Delivered") -> dict[str, str]:
    return {"status": status}


@pytest.mark.parametrize(("age", "expected"), [(7, True), (7.0, True), (8, False)])
def test_return_window_includes_day_seven_and_excludes_day_eight(
    age: int | float, expected: bool
) -> None:
    assert return_eligibility(
        _return_order(),
        elapsed_days=age,
        unopened=True,
        unused=True,
        original_packaging=True,
    ) is expected


@pytest.mark.parametrize(
    ("condition", "value"),
    [("unopened", False), ("unused", False), ("original_packaging", False)],
)
def test_return_requires_all_product_conditions(condition: str, value: bool) -> None:
    conditions = {"unopened": True, "unused": True, "original_packaging": True}
    conditions[condition] = value

    assert return_eligibility(
        _return_order(), elapsed_days=2, **conditions
    ) is False


def test_return_uses_relative_delivery_age_from_order_when_available() -> None:
    order = {"status": "Delivered", "delivered_days_ago": 14}
    assert return_eligibility(
        order,
        unopened=True,
        unused=True,
        original_packaging=True,
    ) is False


@pytest.mark.parametrize(("hours", "expected"), [(48, True), (49, False)])
def test_damage_report_window_boundary(hours: int | float, expected: bool) -> None:
    assert damage_report_eligibility(
        _return_order(), elapsed_hours=hours, photos_provided=True
    ) is expected


def test_damage_report_requires_photos() -> None:
    assert damage_report_eligibility(
        _return_order(), elapsed_hours=1, photos_provided=False
    ) is False


def test_damage_report_rejects_non_delivered_order() -> None:
    assert damage_report_eligibility(
        _return_order("Processing"), elapsed_hours=1, photos_provided=True
    ) is False


def test_delivery_estimate_matches_documented_range() -> None:
    assert delivery_estimate() == "3–5 business days"


@pytest.mark.parametrize("function", [shipping_fee, cod_allowed])
@pytest.mark.parametrize("amount", [-1, True, float("nan"), float("inf"), "500"])
def test_amount_functions_reject_invalid_values(function: object, amount: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        function(amount)  # type: ignore[operator]


@pytest.mark.parametrize("status", [None, "", "  ", 1])
def test_cancellation_rejects_missing_or_malformed_status(status: object) -> None:
    with pytest.raises((TypeError, PolicyInputError)):
        cancellation_eligibility(status)  # type: ignore[arg-type]


def test_return_rejects_missing_or_malformed_facts() -> None:
    with pytest.raises(PolicyInputError, match="elapsed_days"):
        return_eligibility(
            _return_order(), unopened=True, unused=True, original_packaging=True
        )
    with pytest.raises(PolicyInputError, match="unopened"):
        return_eligibility(
            _return_order(),
            elapsed_days=1,
            unopened=None,  # type: ignore[arg-type]
            unused=True,
            original_packaging=True,
        )
    with pytest.raises(PolicyInputError, match="status"):
        return_eligibility(
            {},
            elapsed_days=1,
            unopened=True,
            unused=True,
            original_packaging=True,
        )


def test_damage_report_rejects_missing_or_malformed_facts() -> None:
    with pytest.raises(PolicyInputError, match="status"):
        damage_report_eligibility({}, elapsed_hours=1, photos_provided=True)
    with pytest.raises(PolicyInputError, match="photos_provided"):
        damage_report_eligibility(
            _return_order(), elapsed_hours=1, photos_provided=None  # type: ignore[arg-type]
        )
    with pytest.raises((TypeError, ValueError)):
        damage_report_eligibility(
            _return_order(), elapsed_hours=-1, photos_provided=True
        )


def test_order_based_policy_functions_do_not_mutate_order() -> None:
    order: dict[str, object] = {
        "status": "Delivered",
        "delivered_days_ago": 2,
        "items": ["example"],
    }
    original = deepcopy(order)

    return_eligibility(
        order,
        unopened=True,
        unused=True,
        original_packaging=True,
    )
    damage_report_eligibility(order, elapsed_hours=24, photos_provided=True)

    assert order == original
