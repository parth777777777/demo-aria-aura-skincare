import asyncio
import json
from types import SimpleNamespace as NS

import anyio
from fastapi.testclient import TestClient

from app import main
from app.live.prompt import ARIA_SYSTEM_PROMPT
from app.live.summary import DeterministicSummary, validate_summary


def ws_receive(websocket, timeout=1.0):
    """Read one ASGI websocket frame with a bounded wait and useful failure."""
    async def receive_with_timeout():
        with anyio.fail_after(timeout):
            return await websocket._send_rx.receive()
    try:
        return websocket.portal.call(receive_with_timeout)
    except TimeoutError as error:
        raise AssertionError(f"Timed out after {timeout:.1f}s waiting for a WebSocket frame") from error


def ws_receive_json(websocket, timeout=1.0):
    frame = ws_receive(websocket, timeout)
    if frame.get("type") == "websocket.close":
        raise AssertionError(f"WebSocket closed before expected JSON event (code {frame.get('code')})")
    if not frame.get("text"):
        raise AssertionError(f"Expected JSON WebSocket frame, received {frame.get('type')} frame")
    return json.loads(frame["text"])


class FakeLive:
    def __init__(self, *_):
        self.queue = asyncio.Queue()
        self.audio = []
        self.responses = []
        self.closed = False
        self.connected = False
        self.cancelled = False

    async def connect(self): self.connected = True
    async def send_audio(self, data): self.audio.append(data)
    async def send_tool_response(self, call_id, name, result): self.responses.append((call_id, name, result))
    async def close(self): self.closed = True
    async def events(self):
        try:
            while True:
                item = await self.queue.get()
                if item is None: return
                yield item
        finally:
            self.cancelled = True


def test_prompt_contains_policy_boundaries_and_windows():
    for fact in ("₹499", "3–5", "7 days", "48 hours", "₹2,500"):
        assert fact in ARIA_SYSTEM_PROMPT


def test_summary_validation_and_most_recent_successful_order():
    summary = DeterministicSummary().generate([
        {"name": "get_order_details", "order_id": "ORD-101", "result": {"ok": True}},
        {"name": "get_order_details", "order_id": "ORD-999", "result": {"ok": False}},
    ], [{"role": "user", "text": "track"}])
    assert summary["order_id"] == "ORD-101"
    try:
        validate_summary({"customer_intent": "fake"})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid summary accepted")


def test_ws_start_errors_malformed_session_active_audio_transcripts_tools_cancel_and_goaway(monkeypatch):
    live_instances = []
    class Scripted(FakeLive):
        def __init__(self, *args):
            super().__init__(*args); live_instances.append(self)
        async def send_audio(self, data):
            await super().send_audio(data)
            await self.queue.put(NS(server_content=NS(interim_input_transcription=NS(text="hel"), input_transcription=NS(text="hello"), output_transcription=NS(text="Hi "), model_turn=None, turn_complete=False, interrupted=False)))
            await self.queue.put(NS(server_content=NS(output_transcription=NS(text="there"), model_turn=None, turn_complete=True, interrupted=False)))
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(id="call-1", name="get_order_details", args={"order_id":"ORD-103"}), NS(id="cancelled", name="get_order_details", args={"order_id":"ORD-101"})])))
            await self.queue.put(NS(tool_call_cancellation=NS(ids=["cancelled"])))
            await self.queue.put(NS(go_away=NS(time_left="1s")))
    monkeypatch.setattr(main.app.state, "live_factory", Scripted)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("CALL_IDLE_TIMEOUT_SECONDS", "4")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text("{oops")
            assert ws_receive_json(ws)["code"] == "BAD_MESSAGE"
            ws.send_text('{"type":"start_call"}')
            events = [ws_receive_json(ws), ws_receive_json(ws)]
            assert [event["state"] for event in events] == ["connecting", "live"]
            ws.send_text('{"type":"start_call"}')
            assert ws_receive_json(ws)["code"] == "SESSION_ACTIVE"
            ws.send_bytes(b"pcm")
            got = []
            for _ in range(12):
                event = ws_receive_json(ws)
                got.append(event)
                if event["type"] == "status" and event.get("state") == "ended": break
            assert live_instances[0].audio == [b"pcm"]
            assert live_instances[0].responses[0][0:2] == ("call-1", "get_order_details")
            assert len(live_instances[0].responses) == 1
            assert any(e.get("role") == "user" and e.get("final") is False for e in got)
            assert any(e.get("role") == "user" and e.get("final") is True for e in got)
            assert any(e.get("text") == "Hi there" and e.get("final") is False for e in got)
            assert any(e["type"] == "interrupted" for e in got) is False
            assert got[-1].get("reason") == "session_limit"
    assert live_instances[0].closed


def test_missing_key_fails_start_and_health_stays_available(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(main.app) as client:
        assert client.get("/health").json() == {"status": "healthy"}
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            assert ws_receive_json(ws)["code"] == "GEMINI_UNAVAILABLE"


def test_disconnect_cleans_up_live_session(monkeypatch):
    instances = []
    class Quiet(FakeLive):
        def __init__(self, *args): super().__init__(*args); instances.append(self)
    monkeypatch.setattr(main.app.state, "live_factory", Quiet)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws); ws_receive_json(ws)
        # Exiting the client context closes the websocket without end_call.
    assert instances[0].closed
    assert instances[0].cancelled
    assert main.app.state.active_sessions == 0


def test_live_receive_stream_ending_exits_websocket(monkeypatch):
    instances = []
    class ClosedStream(FakeLive):
        def __init__(self, *args): super().__init__(*args); instances.append(self)
        async def events(self):
            if False: yield None
    monkeypatch.setattr(main.app.state, "live_factory", ClosedStream)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws); ws_receive_json(ws)
            states = []
            while True:
                event = ws_receive_json(ws)
                if event["type"] == "status": states.append(event)
                if event.get("state") == "ended": break
            assert states[-2]["state"] == "ending"
            assert states[-1]["reason"] == "error"
    assert instances[0].closed


def test_end_call_cancels_and_awaits_live_receive_task(monkeypatch):
    instances = []
    class Waiting(FakeLive):
        def __init__(self, *args): super().__init__(*args); instances.append(self)
    monkeypatch.setattr(main.app.state, "live_factory", Waiting)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws); ws_receive_json(ws)
            ws.send_text('{"type":"end_call"}')
            events = []
            while True:
                event = ws_receive_json(ws); events.append(event)
                if event.get("state") == "ended": break
            assert events[-2]["type"] == "summary"
            assert events[-1]["reason"] == "user_ended"
    assert instances[0].cancelled
    assert instances[0].closed


def test_interrupted_audio_provider_error_and_confirmation_guard(monkeypatch):
    instances = []
    class Interrupting(FakeLive):
        def __init__(self, *args): super().__init__(*args); instances.append(self)
        async def send_audio(self, data):
            await self.queue.put(NS(server_content=NS(
                output_transcription=NS(text="Please confirm"),
                model_turn=NS(parts=[NS(inline_data=NS(data=b"speaker-pcm"))]),
                interrupted=True, turn_complete=False)))
            await self.queue.put(RuntimeError("provider failure"))
        async def events(self):
            while True:
                item = await self.queue.get()
                if item is None: return
                if isinstance(item, Exception): raise item
                yield item
    monkeypatch.setattr(main.app.state, "live_factory", Interrupting)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws); ws_receive_json(ws)
            ws.send_bytes(b"input")
            observed = []
            speaker_audio = None
            for _ in range(10):
                frame = ws_receive(ws)
                if frame.get("bytes") is not None:
                    speaker_audio = frame["bytes"]
                    continue
                if frame.get("text"):
                    observed.append(json.loads(frame["text"]))
                    if observed[-1].get("state") == "ended": break
            assert any(e["type"] == "interrupted" for e in observed)
            assert any(e["type"] == "error" and e["code"] == "GEMINI_UNAVAILABLE" for e in observed)
            assert any(e.get("text") == "Please confirm" and e.get("final") is True for e in observed)
            assert speaker_audio == b"speaker-pcm"
    assert instances[0].closed

    from app.tools.registry import execute_tool
    from app.domain.orders import OrderService
    state = {}
    first = execute_tool(OrderService(), "cancel_order", {"order_id": "ORD-103"}, confirmation_state=state, finalized_user_turn=2)
    assert first["error"]["code"] == "CONFIRMATION_REQUIRED"
    same_turn = execute_tool(OrderService(), "cancel_order", {"order_id": "ORD-103"}, confirmation_state=state, finalized_user_turn=2)
    assert same_turn["error"]["code"] == "CONFIRMATION_REQUIRED"
    later_turn = execute_tool(OrderService(), "cancel_order", {"order_id": "ORD-103"}, confirmation_state=state, finalized_user_turn=3)
    assert later_turn["ok"] is True


def test_simultaneous_websocket_sessions_have_separate_carts_orders_and_status(monkeypatch):
    class OrderFlow(FakeLive):
        async def send_audio(self, data):
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(id="cart", name="build_order_cart", args={"items":[{"product_id":"green-tea-face-wash", "quantity":1}], "payment_method":"PREPAID"})])))
            await self.queue.put(NS(server_content=NS(interim_input_transcription=None, input_transcription=NS(text="order"), output_transcription=None, model_turn=None, turn_complete=False, interrupted=False)))
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(id="place", name="place_order", args={"cart_id":"CART-000001"})])))
            await self.queue.put(NS(server_content=NS(interim_input_transcription=None, input_transcription=NS(text="yes"), output_transcription=None, model_turn=None, turn_complete=False, interrupted=False)))
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(id="place-confirmed", name="place_order", args={"cart_id":"CART-000001"})])))
            await self.queue.put(NS(server_content=NS(interim_input_transcription=None, input_transcription=None, output_transcription=None, model_turn=None, turn_complete=False, interrupted=False)))
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(id="cancel", name="cancel_order", args={"order_id":"ORD-201"})])))
            await self.queue.put(NS(server_content=NS(interim_input_transcription=None, input_transcription=NS(text="confirm"), output_transcription=None, model_turn=None, turn_complete=False, interrupted=False)))
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(id="cancel-confirmed", name="cancel_order", args={"order_id":"ORD-201"})])))
            await self.queue.put(NS(server_content=NS(interim_input_transcription=None, input_transcription=None, output_transcription=None, model_turn=None, turn_complete=False, interrupted=False)))
            await self.queue.put(NS(go_away=NS(time_left="1s")))
    monkeypatch.setattr(main.app.state, "live_factory", OrderFlow)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as first, client.websocket_connect("/ws/call") as second:
            for ws in (first, second):
                ws.send_text('{"type":"start_call"}')
                ws_receive_json(ws); ws_receive_json(ws)
                ws.send_bytes(b"audio")
            received = []
            for ws in (first, second):
                events = []
                for _ in range(20):
                    event = ws_receive_json(ws); events.append(event)
                    if event.get("state") == "ended": break
                received.append(events)
            for events in received:
                results = [e["result"] for e in events if e["type"] == "tool_result"]
                assert results[0]["cart"]["cart_id"] == "CART-000001"
                placed = next(result for result in results if result.get("order"))
                cancelled = next(result for result in results if result.get("status") == "Cancelled")
                assert placed["order"]["order_id"] == "ORD-201"
                assert cancelled["status"] == "Cancelled"
