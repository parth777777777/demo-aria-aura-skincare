import json
from unittest.mock import patch

from app.domain.orders import OrderService
from app.tools import registry


def test_all_seven_documented_tools_registered():
    assert set(registry.list_tools()) == {
        "get_order_details", "cancel_order", "check_cancellation_eligibility",
        "check_return_eligibility", "check_damaged_product_eligibility",
        "build_order_cart", "place_order",
    }
    assert {item["name"] for item in registry.get_tool_definitions()} == set(registry.list_tools())
    assert len(registry.list_tools()) == 7


def test_unknown_tool_and_invalid_or_extra_arguments_rejected():
    service = OrderService()
    assert registry.execute_tool(service, "nope", {})["error"]["code"] == "UNKNOWN_TOOL"
    invalid = [None, [], {}, {"order_id": 5}, {"order_id": "ORD-103", "status": "Processing"},
               {"order_id": "ORD-103", "amount": 1}, {"order_id": "ORD-103", "eligible": True}]
    for arguments in invalid:
        assert registry.execute_tool(service, "get_order_details", arguments)["error"]["code"] == "INVALID_ARGUMENTS"
    assert registry.execute_tool(service, "check_return_eligibility", {
        "order_id": "ORD-102", "customer_declared": {"unused": "yes"}
    })["error"]["code"] == "INVALID_ARGUMENTS"


def test_session_service_is_required_and_isolated():
    first, second = OrderService(), OrderService()
    confirmation = {}
    result = registry.execute_tool(first, "cancel_order", {"order_id": "ORD-103"}, confirmation_state=confirmation)
    assert result["error"]["code"] == "CONFIRMATION_REQUIRED"
    result = registry.execute_tool(first, "cancel_order", {"order_id": "ORD-103"}, confirmation_state=confirmation, finalized_user_turn=1)
    assert result["status"] == "Cancelled"
    assert second.get_order_details("ORD-103")["order"]["status"] == "Processing"


def test_delivery_age_is_authoritative_and_non_delivered_reason():
    service = OrderService()
    damage = service.check_damaged_product_eligibility(
        "ORD-102", {"hours_since_delivery": 1, "has_photos": True}
    )
    assert damage == {"ok": True, "eligible": False, "reason": "POLICY_NOT_MET"}
    for order_id in ("ORD-101", "ORD-103"):
        assert service.check_damaged_product_eligibility(order_id, {
            "hours_since_delivery": 1, "has_photos": True
        })["reason"] == "NOT_DELIVERED"
    assert service.check_return_eligibility("ORD-102", {
        "unopened": True, "unused": True, "original_packaging": True
    })["eligible"] is False


def test_cancel_denial_mentions_refusing_delivery_at_doorstep():
    result = OrderService().cancel_order("ORD-101")
    assert result["ok"] is False
    assert "refused at the doorstep" in result["error"]["message"]


def _cart(service, product_id, quantity=1, method="PREPAID"):
    return service.build_order_cart([{"product_id": product_id, "quantity": quantity}], method)


def test_cart_totals_at_shipping_boundaries():
    service = OrderService()
    for product_id, quantity, subtotal, fee in (
        ("green-tea-face-wash", 1, 498, 50),
        ("hydrating-sunscreen-spf50", 1, 499, 50),
        ("aloe-moisturizer", 2, 500, 0),
    ):
        result = _cart(service, product_id, quantity)
        assert result["cart"]["subtotal_inr"] == subtotal
        assert result["cart"]["shipping_fee_inr"] == fee
        assert result["cart"]["total_inr"] == subtotal + fee


def test_cod_boundary_and_placement_rechecks_limit():
    service = OrderService()
    at_limit = service.build_order_cart([{"product_id": "aloe-moisturizer", "quantity": 10}], "COD")
    assert at_limit["cart"]["total_inr"] == 2500
    assert at_limit["cart"]["cod_allowed"] is True
    above = service.build_order_cart([{"product_id": "vitamin-c-serum-30ml", "quantity": 4}], "COD")
    assert above["cart"]["total_inr"] == 2796
    assert above["cart"]["cod_allowed"] is False
    assert service.place_order(above["cart"]["cart_id"])["error"]["code"] == "COD_NOT_ALLOWED"


def test_cart_validation_rejects_bad_quantity_product_and_untrusted_price():
    service = OrderService()
    bad_arguments = [
        {"items": [], "payment_method": "COD"},
        {"items": [{"product_id": "unknown", "quantity": 1}], "payment_method": "COD"},
        {"items": [{"product_id": "hydrating-sunscreen-spf50", "quantity": True}], "payment_method": "COD"},
        {"items": [{"product_id": "hydrating-sunscreen-spf50", "quantity": 1, "price": 1}], "payment_method": "COD"},
        {"items": [{"product_id": "hydrating-sunscreen-spf50", "quantity": 1}], "payment_method": "COD", "total": 0},
    ]
    for arguments in bad_arguments:
        assert registry.execute_tool(service, "build_order_cart", arguments)["ok"] is False


def test_place_order_is_idempotent_visible_cancellable_and_session_local():
    first, second = OrderService(), OrderService()
    cart = _cart(first, "green-tea-face-wash") ["cart"]
    placed = first.place_order(cart["cart_id"])
    repeat = first.place_order(cart["cart_id"])
    assert placed["order"]["order_id"] == "ORD-201"
    assert repeat["idempotent"] is True
    assert first.get_order_details("ORD-201")["order"]["status"] == "Processing"
    guard = {}
    assert registry.execute_tool(first, "cancel_order", {"order_id": "ORD-201"}, confirmation_state=guard)["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert registry.execute_tool(first, "cancel_order", {"order_id": "ORD-201"}, confirmation_state=guard, finalized_user_turn=1)["status"] == "Cancelled"
    assert second.place_order(cart["cart_id"])["error"]["code"] == "CART_NOT_FOUND"
    second_cart = _cart(second, "green-tea-face-wash")["cart"]
    assert second_cart["cart_id"] == "CART-000001"
    assert second.place_order(second_cart["cart_id"])["order"]["order_id"] == "ORD-201"


def test_seed_order_data_is_not_changed_by_cart_flow():
    from app.data.orders import get_order_by_id
    before = [get_order_by_id(f"ORD-{n}") for n in (101, 102, 103)]
    service = OrderService()
    cart = _cart(service, "green-tea-face-wash")["cart"]
    service.place_order(cart["cart_id"])
    assert [get_order_by_id(f"ORD-{n}") for n in (101, 102, 103)] == before


def test_eligibility_structures_boundaries_and_json_results():
    service = OrderService()
    missing = registry.execute_tool(service, "check_return_eligibility", {"order_id": "ORD-102"})
    assert missing == {"ok": True, "eligible": False, "reason": "POLICY_NOT_MET"}
    with patch.object(service, "_current_order", return_value=("ORD-777", {
        "order_id": "ORD-777", "status": "Delivered", "delivered_days_ago": 2,
        "total_inr": 200, "items": [],
    })):
        need_facts = registry.execute_tool(service, "check_return_eligibility", {"order_id": "ORD-777"})
    assert need_facts["eligible"] is None
    assert need_facts["reason"] == "NEEDS_CUSTOMER_CONFIRMATION"
    for day, eligible in ((7, True), (8, False)):
        order = {"status": "Delivered", "delivered_days_ago": day}
        from app.domain.policy import return_eligibility
        assert return_eligibility(order, unopened=True, unused=True, original_packaging=True) is eligible
    from app.domain.policy import damage_report_eligibility
    delivered = {"status": "Delivered"}
    assert damage_report_eligibility(delivered, elapsed_hours=48, photos_provided=True)
    assert not damage_report_eligibility(delivered, elapsed_hours=49, photos_provided=True)
    for tool, args in (
        ("get_order_details", {"order_id": "ORD-103"}),
        ("check_cancellation_eligibility", {"order_id": "ORD-103"}),
        ("check_damaged_product_eligibility", {"order_id": "ORD-103"}),
    ):
        json.dumps(registry.execute_tool(service, tool, args))
