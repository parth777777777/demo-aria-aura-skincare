import json
from unittest.mock import patch

from app.domain.confirmations import PendingActionStore
from app.domain.orders import OrderService
from app.tools import registry


def test_all_nine_documented_tools_registered():
    assert set(registry.list_tools()) == {
        "list_orders", "resolve_order_reference",
        "get_order_details", "cancel_order", "check_cancellation_eligibility",
        "check_return_eligibility", "check_damaged_product_eligibility",
        "build_order_cart", "place_order",
    }
    assert {item["name"] for item in registry.get_tool_definitions()} == set(registry.list_tools())
    assert len(registry.list_tools()) == 9


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


def test_gemini_declarations_are_sanitized_without_weakening_registry():
    from google.genai import types
    from app.live.session import get_gemini_tool_declarations

    allowed = {"type", "description", "properties", "required", "items", "enum",
               "minimum", "maximum", "minItems", "maxItems", "nullable", "format"}

    def assert_sanitized(schema):
        assert set(schema) <= allowed
        for child in schema.get("properties", {}).values():
            assert_sanitized(child)
        if "items" in schema:
            assert_sanitized(schema["items"])

    declarations = get_gemini_tool_declarations()
    assert len(declarations) == 9
    for declaration in declarations:
        assert_sanitized(declaration["parameters"])
        sdk_declaration = types.FunctionDeclaration(**declaration)
        sdk_tool = types.Tool(function_declarations=[sdk_declaration])
        dumped = sdk_tool.model_dump_json(by_alias=True, exclude_none=True)
        assert "additional_properties" not in dumped
        assert "additionalProperties" not in dumped

    by_name = {item["name"]: item for item in declarations}
    assert by_name["get_order_details"]["parameters"]["required"] == ["order_id"]
    assert by_name["list_orders"]["parameters"]["required"] == []
    assert by_name["resolve_order_reference"]["parameters"]["required"] == ["reference"]
    assert by_name["cancel_order"]["parameters"]["required"] == ["order_id"]
    assert by_name["check_cancellation_eligibility"]["parameters"]["required"] == ["order_id"]
    assert by_name["check_return_eligibility"]["parameters"]["required"] == ["order_id"]
    assert by_name["check_damaged_product_eligibility"]["parameters"]["required"] == ["order_id"]
    assert by_name["build_order_cart"]["parameters"]["required"] == ["items", "payment_method"]
    assert by_name["build_order_cart"]["parameters"]["properties"]["payment_method"]["enum"] == ["COD", "PREPAID"]
    assert by_name["place_order"]["parameters"]["required"] == ["cart_id"]

    # Sanitizing declarations must not edit the strict registry schema or its validator.
    assert "additionalProperties" not in by_name["get_order_details"]["parameters"]
    assert registry.get_tool_definitions()[0]["parameters"]["additionalProperties"] is False
    for extra in ("status", "price", "total", "undeclared"):
        result = registry.execute_tool(OrderService(), "get_order_details", {
            "order_id": "ORD-103", extra: "untrusted"
        })
        assert result["error"]["code"] == "INVALID_ARGUMENTS"


def test_session_service_is_required_and_isolated():
    first, second = OrderService(), OrderService()
    confirmation = PendingActionStore()
    result = registry.execute_tool(first, "cancel_order", {"order_id": "ORD-103"}, confirmation_state=confirmation)
    assert result["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert first.get_order_details("ORD-103")["order"]["status"] == "Processing"
    result = registry.execute_tool(first, "cancel_order", {
        "order_id": "ORD-103", "confirmation_id": result["confirmation"]["confirmation_id"]
    }, confirmation_state=confirmation, finalized_user_turn=1)
    assert result["status"] == "Cancelled"
    assert second.get_order_details("ORD-103")["order"]["status"] == "Processing"


def test_confirmation_required_explains_action_was_not_executed_and_names_target():
    service = OrderService()
    state = PendingActionStore()
    cancellation = registry.execute_tool(
        service, "cancel_order", {"order_id": "ORD-103"}, confirmation_state=state)
    assert cancellation["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert "not executed" in cancellation["error"]["message"]
    assert "cancel order ORD-103" in cancellation["error"]["message"]

    cart = service.build_order_cart(
        [{"product_id": "green-tea-face-wash", "quantity": 1}], "PREPAID")["cart"]
    placement = registry.execute_tool(
        service, "place_order", {"cart_id": cart["cart_id"]}, confirmation_state=state)
    assert placement["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert "not executed" in placement["error"]["message"]
    assert f"place cart {cart['cart_id']} for ₹" in placement["error"]["message"]
    assert placement["confirmation"]["details"]["total_inr"] == cart["total_inr"]


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


def test_cart_resolves_normalized_catalog_ids_and_names():
    variants = ("hydrating_sunscreen_spf_50", "Hydrating Sunscreen SPF 50", "hydrating-sunscreen-spf50")
    for variant in variants:
        result = _cart(OrderService(), variant)
        assert result["ok"] is True
        assert result["cart"]["items"][0]["product_id"] == "hydrating-sunscreen-spf50"
        assert result["cart"]["items"][0]["unit_price_inr"] == 499


def test_cart_rejects_unknown_and_ambiguous_normalized_product_names(monkeypatch):
    from app.domain import orders as order_domain

    assert _cart(OrderService(), "not a catalog product")["error"]["code"] == "PRODUCT_NOT_FOUND"
    monkeypatch.setattr(order_domain, "get_products", lambda: {
        "alpha-1": {"id": "alpha-1", "name": "Beta", "price_inr": 100},
        "other": {"id": "other", "name": "Alpha 1", "price_inr": 200},
    })
    ambiguous = _cart(OrderService(), "alpha_1")
    assert ambiguous["error"]["code"] == "AMBIGUOUS_PRODUCT"


def test_build_cart_schema_lists_catalog_ids_and_names():
    from app.data.products import get_products

    definition = next(d for d in registry.get_tool_definitions() if d["name"] == "build_order_cart")
    for product in get_products().values():
        assert product["id"] in definition["description"]
        assert product["name"] in definition["description"]


def test_place_order_is_idempotent_visible_cancellable_and_session_local():
    first, second = OrderService(), OrderService()
    cart = _cart(first, "green-tea-face-wash") ["cart"]
    placed = first.place_order(cart["cart_id"])
    repeat = first.place_order(cart["cart_id"])
    assert placed["order"]["order_id"] == "ORD-201"
    assert repeat["idempotent"] is True
    assert first.get_order_details("ORD-201")["order"]["status"] == "Processing"
    guard = PendingActionStore()
    pending = registry.execute_tool(first, "cancel_order", {"order_id": "ORD-201"}, confirmation_state=guard)
    assert pending["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert registry.execute_tool(first, "cancel_order", {
        "order_id": "ORD-201", "confirmation_id": pending["confirmation"]["confirmation_id"]
    }, confirmation_state=guard, finalized_user_turn=1)["status"] == "Cancelled"
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
