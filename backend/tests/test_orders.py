import json
import tempfile
import unittest
from pathlib import Path

from app.data.orders import OrderDataError, OrderRepository, load_orders


ORDERS_FILE = Path(__file__).resolve().parents[1] / "app" / "data" / "orders.json"


class OrdersDataTests(unittest.TestCase):
    def test_canonical_json_contains_documented_orders_and_fields(self) -> None:
        with ORDERS_FILE.open(encoding="utf-8") as file:
            records = json.load(file)

        self.assertEqual(
            [record["order_id"] for record in records],
            ["ORD-101", "ORD-102", "ORD-103"],
        )
        self.assertEqual(len(records), 3)
        first, second, third = records
        self.assertEqual(first["customer"], "Priya Sharma")
        self.assertEqual(first["items"], ["Vitamin C Serum (30ml)"])
        self.assertEqual(first["total_inr"], 699)
        self.assertEqual(first["status"], "Out for Delivery")
        self.assertEqual(first["carrier"], "BlueDart")
        self.assertEqual(first["tracking_number"], "BD-982103")
        self.assertEqual(first["expected_delivery"], "Today by 6 PM")

        self.assertEqual(second["customer"], "Rahul Verma")
        self.assertEqual(second["items"], ["Hydrating Sunscreen SPF 50"])
        self.assertEqual(second["total_inr"], 499)
        self.assertEqual(second["status"], "Delivered")
        self.assertEqual(second["carrier"], "Delhivery")
        self.assertEqual(second["tracking_number"], "DL-441029")
        self.assertEqual(second["delivered_days_ago"], 14)

        self.assertEqual(third["customer"], "Ananya Patel")
        self.assertEqual(third["items"], ["Green Tea Face Wash", "Green Tea Toner"])
        self.assertEqual(third["total_inr"], 850)
        self.assertEqual(third["status"], "Processing")
        self.assertEqual(third["carrier"], "Not yet assigned")
        self.assertEqual(third["tracking_number"], "Not yet assigned")
        self.assertEqual(third["ordered_hours_ago"], 3)

        self.assertNotIn("delivered_at", second)
        self.assertNotIn("ordered_at", third)

    def test_repository_looks_up_all_seed_orders_and_unknown_id(self) -> None:
        repository = OrderRepository()
        canonical = load_orders()
        for order_id in ("ORD-101", "ORD-102", "ORD-103"):
            with self.subTest(order_id=order_id):
                self.assertEqual(repository.get_order(order_id), canonical[order_id])
        self.assertIsNone(repository.get_order("ORD-999"))

    def test_malformed_json_has_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "malformed-orders.json"
            malformed.write_text("{invalid", encoding="utf-8")
            with self.assertRaisesRegex(OrderDataError, "invalid JSON"):
                load_orders(malformed)

    def test_missing_file_has_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(OrderDataError, "not found"):
                load_orders(Path(directory) / "missing-orders.json")

    def test_invalid_record_structure_has_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid-orders.json"
            invalid.write_text('[{"order_id": "ORD-X"}]', encoding="utf-8")
            with self.assertRaisesRegex(OrderDataError, "missing fields"):
                load_orders(invalid)


if __name__ == "__main__":
    unittest.main()
