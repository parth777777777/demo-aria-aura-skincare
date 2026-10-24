import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.data.orders import get_order_by_id
from app.domain.orders import OrderService
from app.domain import policy


class OrderServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = OrderService()

    def test_lookups_and_policy_results(self) -> None:
        for order_id in ("ORD-101", "ORD-102", "ORD-103"):
            result = self.service.get_order_details(order_id)
            self.assertEqual(set(result), {"ok", "order", "policies"})
            self.assertTrue(result["ok"])
            self.assertEqual(result["order"], get_order_by_id(order_id))
        order = self.service.get_order_details("ord-103")["order"]
        self.assertEqual(
            self.service.get_order_details("ORD-103")["policies"]["cancellation_eligible"],
            policy.cancellation_eligibility(order["status"]),
        )
        self.assertIsNone(self.service.get_order_details("ORD-103")["policies"]["return_eligible"])

    def test_invalid_unknown_and_case_whitespace(self) -> None:
        self.assertEqual(self.service.get_order_details(" ")["error"]["code"], "INVALID_ID")
        self.assertEqual(self.service.get_order_details("ORD-XX")["error"]["code"], "INVALID_ID")
        self.assertEqual(self.service.get_order_details("ORD-999")["error"]["code"], "NOT_FOUND")
        self.assertTrue(self.service.get_order_details(" ord-101 ")["ok"])

    def test_cancel_success_state_repeat_and_seed_immutability(self) -> None:
        data_file = Path(__file__).resolve().parents[1] / "app/data/orders.json"
        before = data_file.read_bytes()
        self.assertEqual(self.service.cancel_order("ORD-103"), {
            "ok": True, "order_id": "ORD-103", "status": "Cancelled"
        })
        self.assertEqual(self.service.get_order_details("ORD-103")["order"]["status"], "Cancelled")
        self.assertEqual(self.service.cancel_order("ORD-103")["error"]["code"], "ALREADY_CANCELLED")
        self.assertEqual(data_file.read_bytes(), before)
        self.assertEqual(json.loads(before)[2]["status"], "Processing")

    def test_denied_cancellation_and_service_isolation(self) -> None:
        for order_id in ("ORD-101", "ORD-102"):
            self.assertEqual(self.service.cancel_order(order_id)["error"]["code"], "NOT_ELIGIBLE")
        self.assertEqual(OrderService().get_order_details("ORD-103")["order"]["status"], "Processing")

    def test_concurrent_cancellation_only_one_fresh_success(self) -> None:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(self.service.cancel_order, ["ORD-103"] * 16))
        self.assertEqual(sum(result["ok"] for result in results), 1)
        self.assertEqual(self.service.get_order_details("ORD-103")["order"]["status"], "Cancelled")


if __name__ == "__main__":
    unittest.main()
