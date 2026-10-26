from types import SimpleNamespace as NS

from scripts.scenario_smoke import (
    check_turn, inspect_event, render_table, return_evidence_path,
    unsupported_payment_terms,
)


def test_check_turn_helpers_accept_and_reject_fake_tool_events():
    assert check_turn("lookup", [{"name": "get_order_details"}], [{"ok": True}]) == []
    assert check_turn("lookup", [{"name": "get_order_details"}], [{"ok": False}])
    assert check_turn("partial", [{"name": "get_order_details"}], [{"ok": False}])
    assert check_turn("weather", [], []) == []
    assert check_turn("weather", [{"name": "get_order_details"}], [{"error": {}}])
    check_call = {"name": "check_return_eligibility", "args": {"order_id": "ORD-102"}}
    check_result = {"ok": True, "eligible": False}
    assert return_evidence_path([check_call], [check_result]) == "check_return_eligibility"
    assert check_turn("return", [check_call], [check_result]) == []
    lookup_call = {"name": "get_order_details", "args": {"order_id": "ORD-102"}}
    lookup_result = {"ok": True, "policies": {"return_eligible": False}}
    assert return_evidence_path([lookup_call], [lookup_result]) == "get_order_details.policies.return_eligible"
    assert check_turn("return", [lookup_call], [lookup_result]) == []
    assert return_evidence_path([], []) == "none"
    assert check_turn("return", [{"name": "place_order"}], [{"ok": False, "eligible": False}])


def test_inspect_event_and_render_table_with_fake_events():
    event = NS(server_content=NS(
        turn_complete=True,
        output_transcription=NS(text="hello"),
        model_turn=NS(parts=[NS(inline_data=NS(data=b"audio"))]),
    ), tool_call=NS(function_calls=[NS(id="c1", name="get_order_details", args={})]),
       go_away=NS(time_left="1s"), session_resumption_update=NS(resumable=True))
    parsed = inspect_event(event)
    assert parsed["complete"] is True
    assert parsed["text"] == "hello"
    assert parsed["audio"] == [b"audio"]
    assert len(parsed["calls"]) == 1
    assert parsed["go_away"].time_left == "1s"
    assert parsed["resumption"].resumable is True
    table = render_table([{"turn": "t1", "tools": ["get_order_details"],
                           "first_audio_ms": 17, "duration_ms": 42,
                           "go_away": False, "resumption": True}])
    assert "t1 | ['get_order_details'] | 17 | 42 | False | True" in table


def test_payment_term_check_matches_plural_and_phrase_stems():
    prompt_policy = "Cash and UPI are offered."
    assert unsupported_payment_terms("We accept credit cards and prepaid cards", prompt_policy) == ["card", "credit card", "prepaid"]
    assert unsupported_payment_terms("Cash or UPI", prompt_policy) == []
