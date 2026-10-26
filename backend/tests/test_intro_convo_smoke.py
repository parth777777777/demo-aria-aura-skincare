import json
from pathlib import Path

from scripts.intro_convo_smoke import (
    build_turn_sequence,
    hash_file,
    json_order,
    result_matches_order,
    turn_is_complete,
)


def test_turn_sequence_uses_given_order_after_four_normal_questions():
    sequence = build_turn_sequence("ORD-777")
    assert len(sequence) == 5
    assert all(role == "customer" for role, _ in sequence)
    assert sequence[-1][1] == "Can you check where my order ORD-777 is?"
    assert "ORD-101" not in sequence[-1][1]


def test_json_order_comparison_checks_expected_fields():
    order = {"status": "Out for Delivery", "total_inr": 699,
             "items": ["Vitamin C Serum (30ml)"], "tracking_number": "BD-982103"}
    matching_tool_result = {"ok": True, "order": dict(order)}
    assert result_matches_order(matching_tool_result, order)
    mismatch = {"ok": True, "order": {**order, "tracking_number": "wrong"}}
    assert not result_matches_order(mismatch, order)
    assert not result_matches_order({"ok": False}, order)


def test_hash_file_detects_temp_json_change(tmp_path: Path):
    path = tmp_path / "orders.json"
    path.write_text(json.dumps([{"order_id": "ORD-101"}]), encoding="utf-8")
    before = hash_file(path)
    path.write_text(json.dumps([{"order_id": "ORD-101", "status": "changed"}]), encoding="utf-8")
    assert before != hash_file(path)


def test_turn_completion_helper_handles_fake_event_list():
    events = [
        {"server_content": {"output_transcription": {"text": "Hello"}}},
        {"server_content": {"turn_complete": True}},
    ]
    assert not turn_is_complete(events[0])
    assert any(turn_is_complete(event) for event in events)


def test_json_order_reads_requested_record_from_temp_file(tmp_path: Path):
    path = tmp_path / "orders.json"
    expected = {"order_id": "ORD-101", "status": "Processing"}
    path.write_text(json.dumps([expected]), encoding="utf-8")
    assert json_order(path, "ORD-101") == expected
