from app.domain.confirmations import PendingActionStore
from app.domain.orders import OrderService
from app.tools.registry import execute_tool


def test_pending_action_requires_immediate_next_turn_and_is_single_use():
    service = OrderService()
    pending = PendingActionStore()
    requested = execute_tool(
        service, "cancel_order", {"order_id": "ORD-103"},
        confirmation_state=pending, finalized_user_turn=4,
    )
    confirmation_id = requested["confirmation"]["confirmation_id"]

    assert requested["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert service.get_order_details("ORD-103")["order"]["status"] == "Processing"

    same_turn = execute_tool(
        service, "cancel_order",
        {"order_id": "ORD-103", "confirmation_id": confirmation_id},
        confirmation_state=pending, finalized_user_turn=4,
    )
    assert same_turn["error"]["code"] == "CONFIRMATION_NOT_READY"
    assert service.get_order_details("ORD-103")["order"]["status"] == "Processing"

    confirmed = execute_tool(
        service, "cancel_order",
        {"order_id": "ORD-103", "confirmation_id": confirmation_id},
        confirmation_state=pending, finalized_user_turn=5,
    )
    assert confirmed == {"ok": True, "order_id": "ORD-103", "status": "Cancelled"}

    replay = execute_tool(
        service, "cancel_order",
        {"order_id": "ORD-103", "confirmation_id": confirmation_id},
        confirmation_state=pending, finalized_user_turn=5,
    )
    assert replay["error"]["code"] == "CONFIRMATION_INVALID"


def test_late_confirmation_is_stale_and_does_not_mutate():
    service = OrderService()
    pending = PendingActionStore()
    requested = execute_tool(
        service, "cancel_order", {"order_id": "ORD-103"},
        confirmation_state=pending, finalized_user_turn=1,
    )

    result = execute_tool(
        service, "cancel_order",
        {"order_id": "ORD-103", "confirmation_id": requested["confirmation"]["confirmation_id"]},
        confirmation_state=pending, finalized_user_turn=3,
    )

    assert result["error"]["code"] == "CONFIRMATION_STALE"
    assert service.get_order_details("ORD-103")["order"]["status"] == "Processing"


def test_confirmation_target_mismatch_invalidates_pending_action():
    service = OrderService()
    pending = PendingActionStore()
    requested = execute_tool(
        service, "cancel_order", {"order_id": "ORD-103"},
        confirmation_state=pending, finalized_user_turn=1,
    )

    result = execute_tool(
        service, "cancel_order",
        {"order_id": "ORD-101", "confirmation_id": requested["confirmation"]["confirmation_id"]},
        confirmation_state=pending, finalized_user_turn=2,
    )

    assert result["error"]["code"] == "CONFIRMATION_MISMATCH"
    assert service.get_order_details("ORD-103")["order"]["status"] == "Processing"
    assert service.get_order_details("ORD-101")["order"]["status"] == "Out for Delivery"


def test_confirmation_expiry_uses_injected_clock():
    now = [0.0]
    pending = PendingActionStore(ttl_seconds=10, clock=lambda: now[0])
    service = OrderService()
    requested = execute_tool(
        service, "cancel_order", {"order_id": "ORD-103"},
        confirmation_state=pending, finalized_user_turn=1,
    )
    now[0] = 10.0

    result = execute_tool(
        service, "cancel_order",
        {"order_id": "ORD-103", "confirmation_id": requested["confirmation"]["confirmation_id"]},
        confirmation_state=pending, finalized_user_turn=2,
    )

    assert result["error"]["code"] == "CONFIRMATION_EXPIRED"
    assert service.get_order_details("ORD-103")["order"]["status"] == "Processing"


def test_changed_cart_details_invalidate_confirmation():
    service = OrderService()
    pending = PendingActionStore()
    cart = service.build_order_cart(
        [{"product_id": "green-tea-face-wash", "quantity": 1}], "PREPAID")["cart"]
    requested = execute_tool(
        service, "place_order", {"cart_id": cart["cart_id"]},
        confirmation_state=pending, finalized_user_turn=1,
    )
    service._carts[cart["cart_id"]]["total_inr"] += 1

    result = execute_tool(
        service, "place_order",
        {"cart_id": cart["cart_id"], "confirmation_id": requested["confirmation"]["confirmation_id"]},
        confirmation_state=pending, finalized_user_turn=2,
    )

    assert result["error"]["code"] == "CONFIRMATION_CHANGED"
    assert service.get_order_details("ORD-201")["error"]["code"] == "NOT_FOUND"


def test_place_order_confirmation_binds_cart_details_and_rechecks_policy():
    service = OrderService()
    pending = PendingActionStore()
    cart = service.build_order_cart(
        [{"product_id": "green-tea-face-wash", "quantity": 1}], "PREPAID")["cart"]

    requested = execute_tool(
        service, "place_order", {"cart_id": cart["cart_id"]},
        confirmation_state=pending, finalized_user_turn=7,
    )
    assert requested["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert requested["confirmation"]["details"]["total_inr"] == cart["total_inr"]
    assert service.get_order_details("ORD-201")["error"]["code"] == "NOT_FOUND"

    confirmed = execute_tool(
        service, "place_order",
        {"cart_id": cart["cart_id"], "confirmation_id": requested["confirmation"]["confirmation_id"]},
        confirmation_state=pending, finalized_user_turn=8,
    )
    assert confirmed["ok"] is True
    assert confirmed["order"]["total_inr"] == cart["total_inr"]


def test_changed_catalog_price_blocks_confirmation_and_requires_rebuilt_cart(monkeypatch):
    import app.domain.orders as order_domain

    service = OrderService()
    pending = PendingActionStore()
    cart = service.build_order_cart(
        [{"product_id": "green-tea-face-wash", "quantity": 1}], "PREPAID")['cart']
    original_get_products = order_domain.get_products

    def changed_catalog():
        products = original_get_products()
        products["green-tea-face-wash"]["price_inr"] += 1
        return products

    monkeypatch.setattr(order_domain, "get_products", changed_catalog)
    blocked = execute_tool(
        service, "place_order", {"cart_id": cart["cart_id"]},
        confirmation_state=pending, finalized_user_turn=1,
    )

    assert blocked["error"]["code"] == "CART_PRICE_CHANGED"
    assert len(pending) == 0
    assert service.get_order_details("ORD-201")["error"]["code"] == "NOT_FOUND"

    rebuilt = service.build_order_cart(
        [{"product_id": "green-tea-face-wash", "quantity": 1}], "PREPAID")['cart']
    assert rebuilt["cart_id"] != cart["cart_id"]
    staged = execute_tool(
        service, "place_order", {"cart_id": rebuilt["cart_id"]},
        confirmation_state=pending, finalized_user_turn=2,
    )
    assert staged["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert staged["confirmation"]["details"]["total_inr"] == rebuilt["total_inr"]
