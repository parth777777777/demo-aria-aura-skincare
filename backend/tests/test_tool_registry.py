import json
from unittest.mock import patch

from app.domain.orders import OrderService
from app.tools import registry


def test_five_documented_tools_registered_and_deferred_tools_absent():
    assert set(registry.list_tools()) == {
        "get_order_details", "cancel_order", "check_cancellation_eligibility",
        "check_return_eligibility", "check_damaged_product_eligibility",
    }
    assert {item["name"] for item in registry.get_tool_definitions()} == set(registry.list_tools())


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
    result = registry.execute_tool(first, "cancel_order", {"order_id": "ORD-103"})
    assert result["status"] == "Cancelled"
    assert second.get_order_details("ORD-103")["order"]["status"] == "Processing"


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
