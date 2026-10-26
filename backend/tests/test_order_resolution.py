from app.data.orders import load_orders
from app.domain.order_resolution import resolve_order_reference
from app.domain.confirmations import PendingActionStore
from app.domain.orders import OrderService
from app.tools.registry import execute_tool


def test_resolves_vitamin_c_aliases_within_candidate_orders():
    candidates = list(load_orders().values())
    for phrase in ("vitamin C", "my vitamin C", "vit C", "my vit C serum"):
        result = resolve_order_reference(phrase, candidates)
        assert result["match_status"] == "matched"
        assert result["order"]["order_id"] == "ORD-101"


def test_order_reference_exact_id_and_vague_context():
    candidates = list(load_orders().values())
    exact = resolve_order_reference("ORD-103", candidates)
    assert exact["match_status"] == "matched"
    assert exact["order"]["order_id"] == "ORD-103"

    context = {"last_order_id": "ORD-101"}
    contextual = resolve_order_reference("that one", candidates, context)
    assert contextual["match_status"] == "matched"
    assert contextual["order"]["order_id"] == "ORD-101"
    assert resolve_order_reference("that one", candidates)["match_status"] == "needs_clarification"


def test_ambiguous_reference_returns_candidates_without_guessing():
    candidates = [
        {"order_id": "ORD-301", "items": ["Vitamin C Serum"], "status": "Processing", "customer": "A"},
        {"order_id": "ORD-302", "items": ["Vitamin C Moisturizer"], "status": "Delivered", "customer": "B"},
    ]

    result = resolve_order_reference("vitamin C", candidates)

    assert result["match_status"] == "ambiguous"
    assert [match["order_id"] for match in result["matches"]] == ["ORD-301", "ORD-302"]
    assert all("customer" not in match for match in result["matches"])


def test_reference_not_found_or_too_vague_never_picks_a_candidate():
    candidates = list(load_orders().values())
    assert resolve_order_reference("unknown product", candidates)["match_status"] == "not_found"
    assert resolve_order_reference("c", candidates)["match_status"] == "needs_clarification"
    assert resolve_order_reference("that one", candidates)["match_status"] == "needs_clarification"


def test_list_orders_and_resolver_tools_are_backend_owned_and_update_structured_context():
    service = OrderService()
    context = {}
    listed = execute_tool(service, "list_orders", {}, conversation_context=context)
    assert listed["ok"] is True
    assert listed["source"] == "mock_db_sample_data"
    assert [order["order_id"] for order in listed["orders"]] == ["ORD-101", "ORD-102", "ORD-103"]
    assert "not associated with a personal identity" in listed["notice"]

    resolved = execute_tool(
        service, "resolve_order_reference", {"reference": "vit C"},
        conversation_context=context,
    )
    assert resolved["match_status"] == "matched"
    assert resolved["order"]["order_id"] == "ORD-101"
    assert context == {"last_order_id": "ORD-101"}

    followup = execute_tool(
        service, "resolve_order_reference", {"reference": "that one"},
        conversation_context=context,
    )
    assert followup["order"]["order_id"] == "ORD-101"


def test_order_service_list_includes_session_overlay_and_new_orders():
    service = OrderService()
    service.cancel_order("ORD-103")
    cart = service.build_order_cart(
        [{"product_id": "green-tea-face-wash", "quantity": 1}], "PREPAID")["cart"]
    service.place_order(cart["cart_id"])

    orders = service.list_orders()
    by_id = {order["order_id"]: order for order in orders}

    assert len(orders) == 4
    assert by_id["ORD-103"]["status"] == "Cancelled"
    assert by_id["ORD-201"]["status"] == "Processing"
    assert load_orders()["ORD-103"]["status"] == "Processing"


def test_account_order_service_is_empty_and_never_falls_back_to_mock_fixtures():
    service = OrderService(owned_orders=[], include_mock_fixtures=False)
    assert service.list_orders() == []
    assert service.get_order_details("ORD-101")["error"]["code"] == "NOT_FOUND"
    assert service.cancel_order("ORD-103")["error"]["code"] == "NOT_FOUND"


def test_account_order_service_mutates_only_its_owned_order_state():
    owned = [{"order_id": "ORD-201", "customer": "Alice", "items": ["Serum"],
              "total_inr": 699, "status": "Processing", "carrier": "Not yet assigned",
              "tracking_number": "Not yet assigned"}]
    service = OrderService(owned_orders=owned, include_mock_fixtures=False)
    confirmation = PendingActionStore()
    staged = execute_tool(service, "cancel_order", {"order_id": "ORD-201"},
                          confirmation_state=confirmation)
    assert staged["error"]["code"] == "CONFIRMATION_REQUIRED"
    result = execute_tool(
        service, "cancel_order", {"order_id": "ORD-201",
        "confirmation_id": staged["confirmation"]["confirmation_id"]},
        finalized_user_turn=1, confirmation_state=confirmation,
    )
    assert result["ok"] is True
    assert service.get_order_details("ORD-201")["order"]["status"] == "Cancelled"
    assert service.get_order_details("ORD-101")["error"]["code"] == "NOT_FOUND"
