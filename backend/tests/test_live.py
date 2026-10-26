import asyncio
import json
import threading
from types import SimpleNamespace as NS

import anyio
from fastapi.testclient import TestClient

from app import main
from app.live.prompt import ARIA_SYSTEM_PROMPT
from app.live.session import GeminiLiveSession
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
        self.text = []
        self.responses = []
        self.closed = False
        self.connected = False
        self.cancelled = False

    async def connect(self): self.connected = True
    async def send_audio(self, data): self.audio.append(data)
    async def send_text(self, text):
        self.text.append(text)
        await self.queue.put(NS(server_content=NS(turn_complete=True)))
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


def test_send_text_uses_client_content_with_explicit_user_role():
    class SDKSession:
        def __init__(self): self.calls = []
        async def send_client_content(self, **kwargs): self.calls.append(("send_client_content", kwargs))
        async def send_realtime_input(self, **kwargs): self.calls.append(("send_realtime_input", kwargs))

    async def exercise():
        wrapper = GeminiLiveSession("unused", "unused")
        wrapper.session = SDKSession()
        await wrapper.send_text("hello")
        assert wrapper.session.calls == [("send_client_content", {
            "turns": {"role": "user", "parts": [{"text": "hello"}]},
            "turn_complete": True,
        })]

    asyncio.run(exercise())


def test_ws_startup_greeting_is_once_after_consumer_ready_and_uses_normal_events(monkeypatch):
    instances = []
    class Greeting(FakeLive):
        def __init__(self, *args):
            super().__init__(*args); self.ready = asyncio.Event(); instances.append(self)
        async def events(self):
            self.ready.set()
            async for event in super().events():
                yield event
        async def send_text(self, text):
            assert self.ready.is_set()
            self.text.append(text)
            await self.queue.put(NS(server_content=NS(
                input_transcription=NS(text="synthetic cue"),
                output_transcription=NS(text="Hello, welcome to Aura."),
                model_turn=NS(parts=[NS(inline_data=NS(data=b"greeting-audio"))]),
                turn_complete=True, interrupted=False)))
    monkeypatch.setattr(main.app.state, "live_factory", Greeting)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            events = []
            for _ in range(8):
                frame = ws_receive(ws)
                if frame.get("bytes") is not None:
                    assert frame["bytes"] == b"greeting-audio"
                    continue
                event = json.loads(frame["text"])
                events.append(event)
                if event.get("text") == "Hello, welcome to Aura." and event.get("final"):
                    break
            assert instances[0].text == ["The customer just connected. Greet them and introduce yourself briefly."]
            assert not any(event.get("role") == "user" for event in events)
            assert any(event.get("role") == "aria" and event.get("final") is False for event in events)
            assert any(event.get("role") == "aria" and event.get("final") is True for event in events)
            ws.send_text('{"type":"end_call"}')
            while ws_receive_json(ws).get("state") != "ended":
                pass

    assert instances[0].ready.is_set()


def test_ws_startup_greeting_failures_and_end_during_send_clean_up(monkeypatch):
    instances = []
    class BrokenConnect(FakeLive):
        def __init__(self, *args): super().__init__(*args); instances.append(self)
        async def connect(self): raise RuntimeError("connect failed")
    monkeypatch.setattr(main.app.state, "live_factory", BrokenConnect)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            assert ws_receive_json(ws)["state"] == "connecting"
            assert ws_receive_json(ws)["code"] == "GEMINI_UNAVAILABLE"
    assert not instances[0].text

    class BrokenGreeting(FakeLive):
        def __init__(self, *args): super().__init__(*args); instances.append(self)
        async def send_text(self, text): raise RuntimeError("send failed")
    monkeypatch.setattr(main.app.state, "live_factory", BrokenGreeting)
    try:
        with TestClient(main.app) as client:
            with client.websocket_connect("/ws/call") as ws:
                ws.send_text('{"type":"start_call"}')
                observed = []
                for _ in range(10):
                    event = ws_receive_json(ws)
                    observed.append(event)
                    if event.get("state") == "ended": break
    except BaseException:
        # Starlette may surface cancellation while the server closes the failed call.
        pass
    assert any(event.get("code") == "GEMINI_UNAVAILABLE" for event in observed)
    assert instances[-1].closed and instances[-1].cancelled
    assert main.app.state.active_sessions == 0

    entered = threading.Event()
    class BlockingGreeting(FakeLive):
        def __init__(self, *args): super().__init__(*args); instances.append(self)
        async def send_text(self, text):
            entered.set()
            await asyncio.Event().wait()
    monkeypatch.setattr(main.app.state, "live_factory", BlockingGreeting)
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws); ws_receive_json(ws)
            assert entered.wait(timeout=1)
            ws.send_text('{"type":"end_call"}')
            while ws_receive_json(ws).get("state") != "ended":
                pass

    assert instances[-1].closed and instances[-1].cancelled
    assert main.app.state.active_sessions == 0


def test_ws_startup_audio_is_held_fifo_and_oldest_frame_dropped(monkeypatch):
    instances = []
    class PendingGreeting(FakeLive):
        def __init__(self, *args):
            super().__init__(*args)
            self.cue_sent = threading.Event()
            self.release = threading.Event()
            self.audio_received = threading.Event()
            instances.append(self)
        async def send_text(self, text):
            self.text.append(text)
            self.cue_sent.set()
        async def events(self):
            try:
                await asyncio.to_thread(self.release.wait)
                yield NS(server_content=NS(turn_complete=True))
                while True:
                    item = await self.queue.get()
                    if item is None: return
                    yield item
            finally:
                self.cancelled = True
        async def send_audio(self, data):
            self.audio.append(data)
            if len(self.audio) == self.expected_count:
                self.audio_received.set()

    monkeypatch.setattr(main.app.state, "live_factory", PendingGreeting)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws); ws_receive_json(ws)
            instance = instances[0]
            instance.expected_count = 4
            assert instance.cue_sent.wait(timeout=1)
            frames = [bytes([n]) for n in (1, 2, 3)]
            for frame in frames:
                ws.send_bytes(frame)
            # A later control response proves all earlier binary frames have
            # been consumed while the fake greeting is still pending.
            ws.send_text('{"type":"start_call"}')
            while ws_receive_json(ws).get("code") != "SESSION_ACTIVE":
                pass
            assert instance.audio == []
            instance.release.set()
            ws.send_bytes(b"trigger")
            assert instance.audio_received.wait(timeout=3)
            assert instance.audio == frames + [b"trigger"]
            ws.send_text('{"type":"end_call"}')
            while ws_receive_json(ws).get("state") != "ended":
                pass

    # Repeat with 101 queued frames: deque(maxlen=100) retains the newest 100.
    instances.clear()
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws); ws_receive_json(ws)
            instance = instances[0]
            instance.expected_count = 101
            assert instance.cue_sent.wait(timeout=1)
            frames = [index.to_bytes(2, "big") for index in range(101)]
            for frame in frames:
                ws.send_bytes(frame)
            ws.send_text('{"type":"start_call"}')
            while ws_receive_json(ws).get("code") != "SESSION_ACTIVE":
                pass
            assert instance.audio == []
            instance.release.set()
            ws.send_bytes(b"trigger")
            assert instance.audio_received.wait(timeout=3)
            assert instance.audio == frames[1:] + [b"trigger"]
            ws.send_text('{"type":"end_call"}')
            while ws_receive_json(ws).get("state") != "ended":
                pass


def test_buffered_audio_uses_shared_counters_and_acknowledgment(monkeypatch, caplog):
    instances = []
    class Pending(FakeLive):
        def __init__(self, *args):
            super().__init__(*args)
            self.release = threading.Event()
            self.cue_sent = threading.Event()
            self.sent_50 = threading.Event()
            instances.append(self)
        async def send_text(self, text):
            self.text.append(text); self.cue_sent.set()
        async def events(self):
            await asyncio.to_thread(self.release.wait)
            yield NS(server_content=NS(turn_complete=True))
            while True:
                item = await self.queue.get()
                if item is None: return
                yield item
        async def send_audio(self, data):
            self.audio.append(data)
            if len(self.audio) == 50: self.sent_50.set()

    monkeypatch.setattr(main.app.state, "live_factory", Pending)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws); ws_receive_json(ws)
            live = instances[0]
            assert live.cue_sent.wait(timeout=1)
            frames = [bytes([index]) * 2 for index in range(50)]
            for frame in frames: ws.send_bytes(frame)
            ws.send_text('{"type":"start_call"}')
            while ws_receive_json(ws).get("code") != "SESSION_ACTIVE": pass
            assert live.audio == []
            live.release.set()
            assert live.sent_50.wait(timeout=2)
            forwarded = ws_receive_json(ws)
            while forwarded.get("type") != "audio_forwarded":
                forwarded = ws_receive_json(ws)
            assert forwarded["frames"] == 50
            assert forwarded["bytes"] == sum(map(len, frames))
            assert live.audio == frames
            ws.send_text('{"type":"end_call"}')
            while ws_receive_json(ws).get("state") != "ended": pass
    assert "binary_frames_received=50" in caplog.text
    assert "binary_bytes_received=100" in caplog.text
    assert "send_audio_successes=50 send_audio_exceptions=0" in caplog.text


def test_buffered_audio_send_failure_uses_normal_gemini_input_error(monkeypatch):
    instances = []
    class PendingFailure(FakeLive):
        def __init__(self, *args):
            super().__init__(*args)
            self.release = threading.Event()
            self.cue_sent = threading.Event()
            instances.append(self)
        async def send_text(self, text):
            self.text.append(text); self.cue_sent.set()
        async def events(self):
            try:
                await asyncio.to_thread(self.release.wait)
                yield NS(server_content=NS(turn_complete=True))
                while True:
                    item = await self.queue.get()
                    if item is None: return
                    yield item
            finally:
                self.cancelled = True
        async def send_audio(self, data): raise RuntimeError("fake send failure")

    monkeypatch.setattr(main.app.state, "live_factory", PendingFailure)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws); ws_receive_json(ws)
            live = instances[0]
            assert live.cue_sent.wait(timeout=1)
            ws.send_bytes(b"buffered")
            ws.send_text('{"type":"start_call"}')
            while ws_receive_json(ws).get("code") != "SESSION_ACTIVE": pass
            live.release.set()
            observed = []
            for _ in range(8):
                event = ws_receive_json(ws)
                observed.append(event)
                if event.get("state") == "ended": break
    error = next(event for event in observed if event.get("type") == "error")
    assert error["code"] == "GEMINI_INPUT_FAILED"
    assert error["recoverable"] is False
    assert live.closed and live.cancelled
    assert main.app.state.active_sessions == 0

def test_events_receives_successive_complete_interactions_and_tool_followup():
    class SDKSession:
        def __init__(self):
            self.cycles = 0
            self.responses = []

        async def receive(self):
            self.cycles += 1
            if self.cycles == 1:
                yield "function-call"
            elif self.cycles == 2:
                yield "tool-follow-up"
            else:
                raise RuntimeError("stop after regression assertions")

        async def send_tool_response(self, **kwargs):
            self.responses.append(kwargs)

    async def exercise():
        wrapper = GeminiLiveSession("unused", "unused")
        wrapper.session = SDKSession()
        events = wrapper.events()
        assert await anext(events) == "function-call"
        await wrapper.send_tool_response("call-1", "get_order_details", {"ok": True})
        assert await anext(events) == "tool-follow-up"
        assert wrapper.session.cycles == 2
        assert len(wrapper.session.responses) == 1
        await events.aclose()

    asyncio.run(exercise())


def test_prompt_contains_policy_boundaries_and_windows():
    prompt = " ".join(ARIA_SYSTEM_PROMPT.split())
    for fact in ("₹499", "3–5", "7 days", "48 hours", "₹2,500"):
        assert fact in prompt
    assert "call cancel_order or" in prompt
    assert "do not ask for confirmation before that first tool call" in prompt
    assert "exact confirmation_id returned by the backend" in prompt
    assert "call list_orders" in prompt
    assert "resolve_order_reference" in prompt
    assert "Never imply a fixture is the caller's personal order" in prompt
    assert "temporary_account source belong to the active demo identity" in prompt
    assert "do not describe them as sample or unlinked" in prompt
    assert "Never say" in prompt and "ok true" in prompt
    assert "State policy facts only from the policy text and tool results" in prompt
    assert "do not invent details" in prompt
    assert "Never guess, complete, or infer an order ID" in prompt
    assert "call get_order_details or the matching eligibility tool before asking questions" in prompt
    assert "never ask for status, dates, or amounts already available from the backend" in prompt


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
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(id="call-1", name="get_order_details", args={"order_id":"ORD-103"}), NS(id="cancelled", name="get_order_details", args={"order_id":"ORD-101"})]), tool_call_cancellation=NS(ids=["cancelled"])))
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
            duplicate_start = ws_receive_json(ws)
            if duplicate_start.get("type") != "error":
                duplicate_start = ws_receive_json(ws)
            assert duplicate_start["code"] == "SESSION_ACTIVE"
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
    import threading

    instances = []
    closed = threading.Event()
    class Quiet(FakeLive):
        def __init__(self, *args): super().__init__(*args); instances.append(self)
        async def close(self):
            await super().close()
            closed.set()
    monkeypatch.setattr(main.app.state, "live_factory", Quiet)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    try:
        with TestClient(main.app) as client:
            with client.websocket_connect("/ws/call") as ws:
                ws.send_text('{"type":"start_call"}')
                ws_receive_json(ws); ws_receive_json(ws)
            # Exiting closes the websocket without end_call.
    except BaseException:
        # Starlette/AnyIO may report cancellation while the disconnect is unwinding.
        pass
    assert closed.wait(timeout=2)
    assert instances[0].closed
    assert instances[0].cancelled
    assert main.app.state.active_sessions == 0


def test_websocket_send_failure_during_finish_still_closes_live(monkeypatch):
    class Socket:
        headers = {}
        def __init__(self):
            self.messages = asyncio.Queue()
            self.closed = False
            self.events = []
        async def accept(self): pass
        async def receive(self): return await self.messages.get()
        async def send_json(self, event):
            self.events.append(event)
            if event.get("state") == "ending": raise RuntimeError("send failed")
        async def close(self, **kwargs): self.closed = True

    instances = []
    class Closing(FakeLive):
        def __init__(self, *args): super().__init__(*args); instances.append(self)
    monkeypatch.setattr(main.app.state, "live_factory", Closing)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    async def exercise():
        ws = Socket()
        await ws.messages.put({"type": "websocket.receive", "text": '{"type":"start_call"}'})
        await ws.messages.put({"type": "websocket.receive", "text": '{"type":"end_call"}'})
        await main.call_socket(ws)
        assert instances[0].closed
    asyncio.run(exercise())


def test_handler_cancellation_mid_cleanup_keeps_live_close_running(monkeypatch):
    class Socket:
        headers = {}
        def __init__(self): self.messages = asyncio.Queue()
        async def accept(self): pass
        async def receive(self): return await self.messages.get()
        async def send_json(self, event): pass
        async def close(self, **kwargs): pass

    async def exercise():
        entered, release, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
        class Closing(FakeLive):
            async def close(self):
                entered.set()
                await release.wait()
                closed.set()
        monkeypatch.setattr(main.app.state, "live_factory", Closing)
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        ws = Socket()
        await ws.messages.put({"type": "websocket.receive", "text": '{"type":"start_call"}'})
        await ws.messages.put({"type": "websocket.disconnect", "code": 1000})
        task = asyncio.create_task(main.call_socket(ws))
        await entered.wait()
        task.cancel()
        release.set()
        try: await task
        except asyncio.CancelledError: pass
        assert closed.is_set()
    asyncio.run(exercise())


def test_end_call_close_error_does_not_emit_error_and_keeps_event_order(monkeypatch):
    instances = []
    class ClosingRaises(FakeLive):
        def __init__(self, *args): super().__init__(*args); instances.append(self)
        async def close(self):
            await self.queue.put(RuntimeError("provider closed"))
            await super().close()
        async def events(self):
            try:
                while True:
                    item = await self.queue.get()
                    if item is None: return
                    if isinstance(item, Exception): raise item
                    yield item
            finally:
                self.cancelled = True
    monkeypatch.setattr(main.app.state, "live_factory", ClosingRaises)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws); ws_receive_json(ws)
            ws.send_text('{"type":"end_call"}')
            received = []
            while True:
                event = ws_receive_json(ws); received.append(event)
                if event.get("state") == "ended": break
    tail = [event for event in received if event.get("type") in {"status", "summary", "error"}]
    assert [event.get("state", event.get("type")) for event in tail[-3:]] == ["ending", "summary", "ended"]
    assert not any(event.get("type") == "error" for event in received)
    assert instances[0].closed
    assert instances[0].cancelled
    assert main.app.state.active_sessions == 0


def test_audio_forwarding_acknowledges_frames_sent_to_live_session(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="app.main")
    instances = []

    class Recording(FakeLive):
        def __init__(self, *args):
            super().__init__(*args)
            instances.append(self)

    monkeypatch.setattr(main.app.state, "live_factory", Recording)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws)
            ws_receive_json(ws)
            for _ in range(50):
                ws.send_bytes(b"x" * 640)
            acknowledgment = ws_receive_json(ws, timeout=2)
            if acknowledgment["type"] == "provider_activity":
                acknowledgment = ws_receive_json(ws, timeout=2)
            assert acknowledgment["type"] == "audio_forwarded"
            assert acknowledgment["frames"] == 50
            assert acknowledgment["bytes"] == 32000
            assert len(instances[0].audio) == 50
            ws.send_text('{"type":"end_call"}')
            while True:
                event = ws_receive_json(ws)
                if event.get("state") == "ended":
                    break
    assert "binary_frames_received=50" in caplog.text
    assert "binary_bytes_received=32000" in caplog.text
    assert "send_audio_successes=50" in caplog.text
    assert "send_audio_exceptions=0" in caplog.text


def test_account_mode_rejects_missing_or_expired_credential_before_gemini(monkeypatch):
    connections = []

    def live_factory(*args):
        connections.append(args)
        return FakeLive(*args)

    monkeypatch.setattr(main.app.state, "live_factory", live_factory)
    monkeypatch.setattr(main.app.state, "demo_session_store", main.DemoSessionStore())
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        for message in (
            {"type": "start_call", "mode": "account"},
            {"type": "start_call", "mode": "account", "credential": "expired"},
        ):
            with client.websocket_connect("/ws/call") as ws:
                ws.send_json(message)
                error = ws_receive_json(ws)
                assert error["type"] == "error"
                assert error["code"] == "ACCOUNT_SESSION_INVALID"
                assert error["recoverable"] is False

    assert connections == []


def test_mock_mode_rejects_invalid_context_id_before_gemini(monkeypatch):
    connections = []

    def live_factory(*args):
        connections.append(args)
        return FakeLive(*args)

    monkeypatch.setattr(main.app.state, "live_factory", live_factory)
    monkeypatch.setattr(main.app.state, "demo_session_store", main.DemoSessionStore())
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_json({"type": "start_call", "mode": "mock_db", "context_id": "expired"})
            error = ws_receive_json(ws)
            assert error["type"] == "error"
            assert error["code"] == "MOCK_SESSION_INVALID"
            assert error["recoverable"] is False

    assert connections == []


def test_account_mode_guessed_mock_order_id_is_not_found(monkeypatch):
    instances = []

    class AccountToolCall(FakeLive):
        def __init__(self, *args):
            super().__init__(*args)
            instances.append(self)

        async def send_text(self, text):
            self.text.append(text)
            await self.queue.put(NS(server_content=NS(turn_complete=True)))
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(
                id="account-tool-1",
                name="get_order_details",
                args={"order_id": "ORD-101"},
            )])))

    monkeypatch.setattr(main.app.state, "live_factory", AccountToolCall)
    monkeypatch.setattr(main.app.state, "demo_session_store", main.DemoSessionStore())
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        credential_response = client.post("/api/demo-sessions", json={"name": "Demo Caller"})
        credential = credential_response.json()["credential"]
        with client.websocket_connect("/ws/call") as ws:
            ws.send_json({"type": "start_call", "mode": "account", "credential": credential})
            events = []
            while not any(event.get("type") == "tool_result" for event in events):
                events.append(ws_receive_json(ws))
            result = next(event["result"] for event in events if event.get("type") == "tool_result")
            assert result["ok"] is False
            assert result["error"]["code"] == "NOT_FOUND"
            assert "Vitamin C" not in json.dumps(result)
            assert instances[0].responses[0][2] == result
            ws.send_json({"type": "end_call"})
            while ws_receive_json(ws).get("state") != "ended":
                pass


def test_account_carts_persist_across_calls_and_remain_identity_scoped(monkeypatch):
    starts = [0]

    class AccountCart(FakeLive):
        async def send_text(self, text):
            self.text.append(text)
            await self.queue.put(NS(server_content=NS(turn_complete=True)))
            starts[0] += 1
            if starts[0] == 1:
                await self.queue.put(NS(tool_call=NS(function_calls=[NS(
                    id="cart-1", name="build_order_cart",
                    args={"items": [{"product_id": "green-tea-face-wash", "quantity": 1}],
                          "payment_method": "PREPAID"},
                )])))
            else:
                await self.queue.put(NS(tool_call=NS(function_calls=[NS(
                    id=f"list-carts-{starts[0]}", name="list_order_carts", args={},
                )])))

    monkeypatch.setattr(main.app.state, "live_factory", AccountCart)
    store = main.DemoSessionStore()
    monkeypatch.setattr(main.app.state, "demo_session_store", store)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        credential = client.post("/api/demo-sessions", json={"name": "Cart Owner"}).json()["credential"]
        for expected_id in ("CART-000001", None, None):
            token = credential
            if starts[0] == 2:
                token = client.post("/api/demo-sessions", json={"name": "Other Owner"}).json()["credential"]
            with client.websocket_connect("/ws/call") as ws:
                ws.send_json({"type": "start_call", "mode": "account", "credential": token})
                events = []
                while not any(event.get("type") == "tool_result" for event in events):
                    events.append(ws_receive_json(ws))
                result = next(event["result"] for event in events if event.get("type") == "tool_result")
                assert result["ok"] is True
                if expected_id is not None:
                    assert result["cart"]["cart_id"] == expected_id
                elif token == credential:
                    assert [cart["cart_id"] for cart in result["carts"]] == ["CART-000001"]
                    assert result["carts"][0]["placement_status"] == "ready"
                else:
                    assert result["carts"] == []
                ws.send_json({"type": "end_call"})
                while ws_receive_json(ws).get("state") != "ended":
                    pass

        identity = store.authorize(credential, expected_mode="account")
        assert [cart["cart_id"] for cart in identity["carts"]] == ["CART-000001"]
        assert identity["orders"] == []


def test_account_order_placement_confirms_persists_and_retries_idempotently(monkeypatch):
    store = main.DemoSessionStore()
    credential, _ = store.create("Order Owner")
    seed = main.OrderService(include_mock_fixtures=False)
    cart = seed.build_order_cart(
        [{"product_id": "green-tea-toner", "quantity": 1}], "PREPAID"
    )["cart"]
    assert store.replace_account_carts(credential, [cart])
    call_count = [0]

    class AccountPlacement(FakeLive):
        async def send_audio(self, data):
            call_count[0] += 1
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(
                id=f"place-{call_count[0]}", name="place_order",
                args={"cart_id": cart["cart_id"]},
            )])))

        async def _user_turn(self, text):
            await self.queue.put(NS(server_content=NS(
                input_transcription=NS(text=text), turn_complete=False,
            )))

        async def send_tool_response(self, call_id, name, result):
            await super().send_tool_response(call_id, name, result)
            if result.get("error", {}).get("code") == "CONFIRMATION_REQUIRED":
                confirmation = result["confirmation"]
                await self._user_turn("yes, I confirm")
                await self.queue.put(NS(tool_call=NS(function_calls=[NS(
                    id="confirmed-place", name="place_order",
                    args={**confirmation["target"],
                          "confirmation_id": confirmation["confirmation_id"]},
                )])))
            elif result.get("ok"):
                await self.queue.put(NS(go_away=NS(time_left="1s")))

    monkeypatch.setattr(main.app.state, "live_factory", AccountPlacement)
    monkeypatch.setattr(main.app.state, "demo_session_store", store)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        observed = []
        for attempt in range(2):
            with client.websocket_connect("/ws/call") as ws:
                ws.send_json({"type": "start_call", "mode": "account", "credential": credential})
                ws_receive_json(ws); ws_receive_json(ws)
                ws.send_bytes(b"synthetic audio")
                events = []
                for _ in range(30):
                    event = ws_receive_json(ws)
                    events.append(event)
                    if event.get("state") == "ended":
                        break
                observed.append([event["result"] for event in events if event.get("type") == "tool_result"])

    first_results, retry_results = observed
    assert first_results[0]["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert first_results[1]["ok"] is True
    assert first_results[1]["idempotent"] is False
    assert first_results[1]["order"]["order_id"] == "ORD-201"
    assert first_results[1]["order"]["customer"] == "Order Owner"
    assert retry_results == [{
        "ok": True, "order": first_results[1]["order"], "idempotent": True
    }]
    identity = store.authorize(credential, expected_mode="account")
    assert [order["order_id"] for order in identity["orders"]] == ["ORD-201"]


def test_unrelated_turn_after_placement_quote_does_not_place_order(monkeypatch):
    store = main.DemoSessionStore()
    credential, _ = store.create("No Placement")
    seed = main.OrderService(include_mock_fixtures=False)
    cart = seed.build_order_cart(
        [{"product_id": "green-tea-toner", "quantity": 1}], "PREPAID"
    )["cart"]
    assert store.replace_account_carts(credential, [cart])

    class UnrelatedTurn(FakeLive):
        async def send_audio(self, data):
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(
                id="place", name="place_order", args={"cart_id": cart["cart_id"]},
            )])))

        async def send_tool_response(self, call_id, name, result):
            await super().send_tool_response(call_id, name, result)
            if result.get("error", {}).get("code") == "CONFIRMATION_REQUIRED":
                # Script the provider's next decision: the user changes topic,
                # so it must not issue the confirmation-bearing mutation call.
                await self.queue.put(NS(server_content=NS(
                    input_transcription=NS(text="What are your delivery hours?"),
                    turn_complete=False,
                )))
                await self.queue.put(NS(go_away=NS(time_left="1s")))

    monkeypatch.setattr(main.app.state, "live_factory", UnrelatedTurn)
    monkeypatch.setattr(main.app.state, "demo_session_store", store)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_json({"type": "start_call", "mode": "account", "credential": credential})
            ws_receive_json(ws); ws_receive_json(ws)
            ws.send_bytes(b"synthetic audio")
            events = []
            for _ in range(30):
                event = ws_receive_json(ws)
                events.append(event)
                if event.get("state") == "ended":
                    break

    results = [event["result"] for event in events if event.get("type") == "tool_result"]
    assert len(results) == 1
    assert results[0]["error"]["code"] == "CONFIRMATION_REQUIRED"
    identity = store.authorize(credential, expected_mode="account")
    assert identity["orders"] == []


def test_mock_db_start_call_without_mode_remains_supported(monkeypatch):
    instances = []

    class Recording(FakeLive):
        def __init__(self, *args):
            super().__init__(*args)
            instances.append(self)

    monkeypatch.setattr(main.app.state, "live_factory", Recording)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_json({"type": "start_call"})
            assert ws_receive_json(ws)["state"] == "connecting"
            assert ws_receive_json(ws)["state"] == "live"
            ws.send_json({"type": "end_call"})
            while ws_receive_json(ws).get("state") != "ended":
                pass

    assert instances and instances[0].connected


def test_order_listing_and_resolution_are_scoped_and_context_survives_session_calls(monkeypatch):
    instances = []

    class OrderQueries(FakeLive):
        def __init__(self, *args):
            super().__init__(*args)
            self.index = len(instances)
            instances.append(self)

        async def send_audio(self, data):
            if self.index == 0:
                await self._user_turn("list my orders")
                await self._tool("list-1", "list_orders", {})
                await self._user_turn("vit C")
                await self._tool("resolve-1", "resolve_order_reference", {"reference": "vit C"})
            elif self.index == 1:
                await self._user_turn("that one")
                await self._tool("resolve-2", "resolve_order_reference", {"reference": "that one"})
            else:
                await self._user_turn("list my orders")
                await self._tool("list-account", "list_orders", {})
                await self._user_turn("vit C")
                await self._tool("resolve-account", "resolve_order_reference", {"reference": "vit C"})

        async def _user_turn(self, text):
            await self.queue.put(NS(server_content=NS(input_transcription=NS(text=text))))

        async def _tool(self, call_id, name, args):
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(
                id=call_id, name=name, args=args,
            )])))

    monkeypatch.setattr(main.app.state, "live_factory", OrderQueries)
    monkeypatch.setattr(main.app.state, "demo_session_store", main.DemoSessionStore())
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    with TestClient(main.app) as client:
        mock_context = client.post("/api/mock-sessions").json()["context_id"]
        account_credential = client.post(
            "/api/demo-sessions", json={"name": "Account Caller"}
        ).json()["credential"]

        def call(payload, expected_results):
            with client.websocket_connect("/ws/call") as ws:
                ws.send_json({"type": "start_call", **payload})
                while ws_receive_json(ws).get("state") != "live":
                    pass
                ws.send_bytes(b"query")
                results = {}
                while len(results) < expected_results:
                    event = ws_receive_json(ws)
                    if event.get("type") == "tool_result":
                        results[event["name"] if event["name"] == "list_orders" else event["call_id"]] = event["result"]
                ws.send_json({"type": "end_call"})
                while ws_receive_json(ws).get("state") != "ended":
                    pass
                return results

        first = call({"mode": "mock_db", "context_id": mock_context}, 2)
        first_list = first["list_orders"]
        first_resolve = first["resolve-1"]
        assert first_list["source"] == "mock_db_sample_data"
        assert [order["order_id"] for order in first_list["orders"]] == ["ORD-101", "ORD-102", "ORD-103"]
        assert "not associated with a personal identity" in first_list["notice"]
        assert first_resolve["match_status"] == "matched"
        assert first_resolve["order"]["order_id"] == "ORD-101"

        second = call({"mode": "mock_db", "context_id": mock_context}, 1)
        assert second["resolve-2"]["match_status"] == "matched"
        assert second["resolve-2"]["order"]["order_id"] == "ORD-101"

        account = call({"mode": "account", "credential": account_credential}, 2)
        assert account["list_orders"]["source"] == "temporary_account"
        assert account["list_orders"]["orders"] == []
        assert account["resolve-account"]["match_status"] == "not_found"
        assert "ORD-101" not in json.dumps(account)


def test_websocket_logs_effective_model_and_call_summary(monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="app.main")
    monkeypatch.setattr(main.app.state, "live_factory", FakeLive)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("GEMINI_LIVE_MODEL", "gemini-test-model")
    with TestClient(main.app) as client:
        with client.websocket_connect("/ws/call") as ws:
            ws.send_text('{"type":"start_call"}')
            ws_receive_json(ws)
            ws_receive_json(ws)
            ws.send_text('{"type":"end_call"}')
            while ws_receive_json(ws).get("state") != "ended":
                pass
    assert "websocket call connected model=gemini-test-model" in caplog.text
    assert "call summary model=gemini-test-model" in caplog.text
    assert "binary_frames_received=0 binary_bytes_received=0" in caplog.text
    assert "send_audio_successes=0 send_audio_exceptions=0" in caplog.text
    assert "provider_events=" in caplog.text


def test_app_info_logging_does_not_raise_root_level():
    import logging

    assert logging.getLogger("app").level == logging.INFO
    assert logging.getLogger().level != logging.INFO


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
            try:
                while True:
                    item = await self.queue.get()
                    if item is None: return
                    if isinstance(item, Exception): raise item
                    yield item
            finally:
                self.cancelled = True
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
    assert instances[0].cancelled
    assert main.app.state.active_sessions == 0

    from app.tools.registry import execute_tool
    from app.domain.orders import OrderService
    from app.domain.confirmations import PendingActionStore
    state = PendingActionStore()
    first = execute_tool(OrderService(), "cancel_order", {"order_id": "ORD-103"}, confirmation_state=state, finalized_user_turn=2)
    assert first["error"]["code"] == "CONFIRMATION_REQUIRED"
    confirmation_id = first["confirmation"]["confirmation_id"]
    same_turn = execute_tool(OrderService(), "cancel_order", {
        "order_id": "ORD-103", "confirmation_id": confirmation_id
    }, confirmation_state=state, finalized_user_turn=2)
    assert same_turn["error"]["code"] == "CONFIRMATION_NOT_READY"
    later_turn = execute_tool(OrderService(), "cancel_order", {
        "order_id": "ORD-103", "confirmation_id": confirmation_id
    }, confirmation_state=state, finalized_user_turn=3)
    assert later_turn["ok"] is True


def test_simultaneous_websocket_sessions_have_separate_carts_orders_and_status(monkeypatch):
    class OrderFlow(FakeLive):
        async def send_audio(self, data):
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(
                id="cart", name="build_order_cart", args={
                    "items": [{"product_id": "green-tea-face-wash", "quantity": 1}],
                    "payment_method": "PREPAID",
                })])))
            await self._user_turn("place an order")
            await self.queue.put(NS(tool_call=NS(function_calls=[NS(
                id="place", name="place_order", args={"cart_id": "CART-000001"})])))

        async def _user_turn(self, text):
            await self.queue.put(NS(server_content=NS(
                interim_input_transcription=None,
                input_transcription=NS(text=text),
                output_transcription=None,
                model_turn=None,
                turn_complete=False,
                interrupted=False,
            )))

        async def send_tool_response(self, call_id, name, result):
            await super().send_tool_response(call_id, name, result)
            if result.get("error", {}).get("code") == "CONFIRMATION_REQUIRED":
                confirmation = result["confirmation"]
                await self._user_turn("yes, I confirm")
                await self.queue.put(NS(tool_call=NS(function_calls=[NS(
                    id=f"confirm-{call_id}", name=name,
                    args={**confirmation["target"],
                          "confirmation_id": confirmation["confirmation_id"]},
                )])))
            elif name == "place_order" and result.get("ok"):
                await self._user_turn("cancel ORD-201")
                await self.queue.put(NS(tool_call=NS(function_calls=[NS(
                    id="cancel", name="cancel_order", args={"order_id": "ORD-201"})])))
            elif name == "cancel_order" and result.get("ok"):
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
                for _ in range(40):
                    event = ws_receive_json(ws); events.append(event)
                    if event.get("state") == "ended": break
                received.append(events)
            for events in received:
                results = [e["result"] for e in events if e["type"] == "tool_result"]
                assert results[0]["cart"]["cart_id"] == "CART-000001"
                assert sum(result.get("error", {}).get("code") == "CONFIRMATION_REQUIRED" for result in results) == 2
                placed = next(result for result in results if result.get("order"))
                cancelled = next(result for result in results if result.get("status") == "Cancelled")
                assert placed["order"]["order_id"] == "ORD-201"
                assert cancelled["status"] == "Cancelled"
