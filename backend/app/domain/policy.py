"""Pure Aura Skincare policy functions."""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any


class PolicyInputError(ValueError):
    """Raised when a policy decision lacks valid required inputs."""


def _amount(value: Any, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise TypeError(f"{name} must be a number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{name} must be a finite, non-negative number") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{name} must be a finite, non-negative number")
    return amount


def _duration(value: Any, name: str) -> Decimal:
    duration = _amount(value, name)
    return duration


def _order_status(order: Mapping[str, Any]) -> str:
    if not isinstance(order, Mapping):
        raise TypeError("order must be a mapping")
    status = order.get("status")
    if not isinstance(status, str) or not status.strip():
        raise PolicyInputError("order must contain a non-empty string status")
    return status.strip().casefold()


def _required_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyInputError(f"{name} must be provided as a boolean")
    return value


def shipping_fee(amount: int | float | Decimal) -> int:
    """Return ₹50 for totals at or below ₹499 and ₹0 above it."""
    total = _amount(amount, "amount")
    threshold = Decimal("499")
    return 50 if total <= threshold else 0


def delivery_estimate() -> str:
    """Return the documented standard-delivery estimate."""
    return "3–5 business days"


def cancellation_eligibility(status: str) -> bool:
    """Return whether an order status permits cancellation.

    Status matching ignores surrounding whitespace and letter case. Unknown,
    non-empty statuses are ineligible; missing or malformed statuses are errors.
    """
    if not isinstance(status, str):
        raise TypeError("status must be a string")
    normalized = status.strip().casefold()
    if not normalized:
        raise PolicyInputError("status must not be empty")
    return normalized == "processing"


def return_eligibility(
    order: Mapping[str, Any],
    *,
    unopened: bool | None = None,
    unused: bool | None = None,
    original_packaging: bool | None = None,
    elapsed_days: int | float | Decimal | None = None,
) -> bool:
    """Check the 7-day return window and documented product conditions.

    ``elapsed_days`` is preferred when supplied; otherwise the documented
    relative ``delivered_days_ago`` value on the order is used. Day 7 is
    included. Product condition facts must be supplied explicitly.
    """
    status = _order_status(order)
    if elapsed_days is None:
        elapsed_days = order.get("delivered_days_ago")
    if elapsed_days is None:
        raise PolicyInputError("elapsed_days or order.delivered_days_ago is required")
    age = _duration(elapsed_days, "elapsed_days")
    conditions = (
        _required_bool(unopened, "unopened"),
        _required_bool(unused, "unused"),
        _required_bool(original_packaging, "original_packaging"),
    )
    return status == "delivered" and age <= Decimal("7") and all(conditions)


def damage_report_eligibility(
    order: Mapping[str, Any],
    *,
    elapsed_hours: int | float | Decimal | None = None,
    photos_provided: bool | None = None,
) -> bool:
    """Check the 48-hour damage-report window and photo-evidence requirement.

    ``elapsed_hours`` must be supplied explicitly because the canonical seed
    orders do not record delivery time at this precision. Exactly 48 hours is
    included.
    """
    status = _order_status(order)
    if elapsed_hours is None:
        raise PolicyInputError("elapsed_hours is required")
    hours = _duration(elapsed_hours, "elapsed_hours")
    has_photos = _required_bool(photos_provided, "photos_provided")
    return status == "delivered" and hours <= Decimal("48") and has_photos


def cod_allowed(amount: int | float | Decimal) -> bool:
    """Return whether COD is available for a non-negative order total up to ₹2,500."""
    total = _amount(amount, "amount")
    return total <= Decimal("2500")
