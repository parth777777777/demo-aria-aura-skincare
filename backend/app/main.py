"""Aura HTTP health endpoint and isolated per-connection call transport."""
import asyncio
import json
import logging
import os
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.domain.orders import OrderService
from app.live.session import GeminiLiveSession
from app.live.summary import DeterministicSummary
from app.tools.registry import execute_tool

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
# Keep application INFO logging scoped to this namespace; do not change root.
app_logger = logging.getLogger("app")
app_logger.setLevel(logging.INFO)
if not app_logger.handlers:
    app_handler = logging.StreamHandler()
    app_handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    app_logger.addHandler(app_handler)
logger = logging.getLogger(__name__)
app = FastAPI(title="Aura Skincare API")
app.state.live_factory = GeminiLiveSession
app.state.active_sessions = 0
app.state.session_lock = asyncio.Lock()


def _setting(name: str, default: str) -> str:
    return os.getenv(name, default)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


def _get(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        if value is not None:
            return value
    return default


@app.websocket("/ws/call")
async def call_socket(websocket: WebSocket) -> None:
    origins = {x.strip() for x in _setting("ALLOWED_WS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()}
    origin = websocket.headers.get("origin")
    if origin and origin not in origins:
        await websocket.close(code=1008, reason="Origin not allowed")
        return
    await websocket.accept()
    live = None
    event_task: asyncio.Task[None] | None = None
    greeting_task: asyncio.Task[None] | None = None
    live_closed = asyncio.Event()
    provider_ready = asyncio.Event()
    greeting_done = asyncio.Event()
    greeting_pending = False
    customer_audio_started = False
    startup_audio: deque[bytes] = deque(maxlen=100)
    acquired = False
    lock = asyncio.Lock()
    started: float | None = None
    max_duration = int(_setting("MAX_CALL_DURATION_SECONDS", "600"))
    idle_timeout = int(_setting("CALL_IDLE_TIMEOUT_SECONDS", "120"))
    tools: list[dict[str, Any]] = []
    transcript: list[dict[str, str]] = []
    confirmation: dict[tuple[str, str], int] = {}
    user_turn = 0
    output_turn = 0
    output_text = ""
    ended = False
    audio_frames_forwarded = 0
    audio_bytes_forwarded = 0
    binary_frames_received = 0
    binary_bytes_received = 0
    send_audio_successes = 0
    send_audio_exceptions = 0
    max_send_audio_duration_ms = 0.0
    provider_event_count = 0
    provider_field_counts: Counter[str] = Counter()
    call_model = "unknown"
    config_field_names: list[str] = []

    async def emit(event_type: str, **data: Any) -> None:
        async with lock:
            await websocket.send_json({"type": event_type, **data, "ts": datetime.now(timezone.utc).isoformat()})

    async def finish(reason: str) -> None:
        nonlocal ended
        if ended:
            return
        ended = True
        await emit("status", state="ending", reason=reason)
        if output_text:
            transcript.append({"role": "aria", "text": output_text})
            await emit("transcript", turn_id=f"a{output_turn}", role="aria", text=output_text, final=True)
        try:
            summary = DeterministicSummary().generate(tools, transcript)
            await emit("summary", summary=summary)
        except (ValueError, TypeError):
            await emit("error", code="INTERNAL", message="Call summary could not be validated.", recoverable=True)
        await emit("status", state="ended", reason=reason)
        try:
            await websocket.close()
        except Exception:
            pass

    async def provider_events() -> None:
        try:
            await _consume_provider_events()
        except Exception:
            if not ended:
                await emit("error", code="GEMINI_UNAVAILABLE", message="The Gemini session ended unexpectedly.", recoverable=True)
                await finish("error")
        finally:
            live_closed.set()

    async def _consume_provider_events() -> None:
        nonlocal output_turn, output_text, user_turn, provider_event_count
        provider_ready.set()
        async for event in live.events():
            if ended:
                return
            provider_event_count += 1
            content = _get(event, "server_content", "serverContent")
            input_transcription = _get(content, "input_transcription", "inputTranscription") if content else None
            output_transcription = _get(content, "output_transcription", "outputTranscription") if content else None
            model_turn = _get(content, "model_turn", "modelTurn") if content else None
            model_audio = any(
                _get(_get(part, "inline_data", "inlineData"), "data")
                for part in (_get(model_turn, "parts", default=[]) or [])
            ) if model_turn else False
            present_fields = [
                name for name, value in (
                    ("setup_complete", _get(event, "setup_complete", "setupComplete")),
                    ("server_content", content),
                    ("input_transcription", input_transcription),
                    ("output_transcription", output_transcription),
                    ("model_turn_audio", model_audio),
                    ("tool_call", _get(event, "tool_call", "toolCall")),
                    ("go_away", _get(event, "go_away", "goAway")),
                    ("session_resumption_update", _get(event, "session_resumption_update", "sessionResumptionUpdate")),
                ) if value
            ]
            provider_field_counts.update(present_fields)
            if provider_event_count <= 10:
                logger.info("provider event #%d present_fields=%s", provider_event_count, present_fields)
            logger.info("provider event counts=%s", dict(provider_field_counts))
            if provider_event_count == 1:
                await emit("provider_activity")
            cancellation = _get(event, "tool_call_cancellation", "toolCallCancellation")
            cancelled = _get(cancellation, "ids", default=[]) or [] if cancellation else []
            cancelled_ids.update(cancelled)
            content = _get(event, "server_content", "serverContent")
            if content:
                # The startup cue is sent as user-role client content by the
                # SDK adapter. Suppress its input-side transcription so it can
                # never become a customer transcript or advance confirmation.
                if not customer_audio_started:
                    interim = None
                    final_input = None
                else:
                    interim = _get(content, "interim_input_transcription", "interimInputTranscription")
                    final_input = _get(content, "input_transcription", "inputTranscription")
                for transcription, final in ((interim, False), (final_input, True)):
                    text = _get(transcription, "text") if transcription else None
                    if text:
                        if final:
                            user_turn += 1
                            transcript.append({"role": "user", "text": text})
                        await emit("transcript", turn_id=f"u{user_turn + (0 if final else 1)}", role="user", text=text, final=final)
                out = _get(content, "output_transcription", "outputTranscription")
                out_text = _get(out, "text") if out else None
                if out_text:
                    if not output_text:
                        output_turn += 1
                    output_text += out_text
                    await emit("transcript", turn_id=f"a{output_turn}", role="aria", text=output_text, final=False)
                model_turn = _get(content, "model_turn", "modelTurn")
                for part in _get(model_turn, "parts", default=[]) or []:
                    inline = _get(part, "inline_data", "inlineData")
                    audio = _get(inline, "data") if inline else None
                    if audio:
                        async with lock:
                            await websocket.send_bytes(audio)
                if _get(content, "interrupted", default=False):
                    if output_text:
                        transcript.append({"role": "aria", "text": output_text})
                        await emit("transcript", turn_id=f"a{output_turn}", role="aria", text=output_text, final=True)
                        output_text = ""
                    await emit("interrupted")
                if _get(content, "turn_complete", "turnComplete", default=False) and output_text:
                    transcript.append({"role": "aria", "text": output_text})
                    await emit("transcript", turn_id=f"a{output_turn}", role="aria", text=output_text, final=True)
                    output_text = ""
                if _get(content, "turn_complete", "turnComplete", default=False) and greeting_pending:
                    greeting_done.set()
            tool_call = _get(event, "tool_call", "toolCall")
            if tool_call:
                calls = _get(tool_call, "function_calls", "functionCalls", default=[]) or []
                for call in calls:
                    call_id = _get(call, "id")
                    if not call_id or call_id in cancelled_ids:
                        continue
                    await dispatch_tool(call_id, call)
            if _get(event, "go_away", "goAway"):
                await finish("session_limit")
                return

    async def dispatch_tool(call_id: str, call: Any) -> None:
        name, args = _get(call, "name", default=""), _get(call, "args", default={})
        await emit("tool_call", call_id=call_id, name=name, args=args)
        result = execute_tool(service, name, args, confirmation_state=confirmation, finalized_user_turn=user_turn)
        order_id = (result.get("order_id") or result.get("order", {}).get("order_id")
                    or (args.get("order_id") if isinstance(args, dict) else None))
        tools.append({"name": name, "order_id": order_id, "result": result})
        await emit("tool_result", call_id=call_id, name=name, result=result)
        if call_id not in cancelled_ids:
            await live.send_tool_response(call_id, name, result)

    async def send_startup_greeting() -> None:
        try:
            await provider_ready.wait()
            if ended:
                return
            await live.send_text("The customer just connected. Greet them and introduce yourself briefly.")
        except asyncio.CancelledError:
            raise
        except Exception:
            if not ended:
                await emit("error", code="GEMINI_UNAVAILABLE", message="Could not start the greeting.", recoverable=True)
                await finish("error")
        finally:
            if ended:
                greeting_done.set()

    async def forward_audio(frame: bytes) -> bool:
        nonlocal customer_audio_started
        nonlocal send_audio_successes, send_audio_exceptions
        nonlocal max_send_audio_duration_ms, audio_frames_forwarded, audio_bytes_forwarded
        customer_audio_started = True
        send_started = time.perf_counter()
        try:
            await live.send_audio(frame)
            send_audio_successes += 1
        except Exception as exc:
            send_audio_exceptions += 1
            error_message = str(exc)
            api_key = _setting("GEMINI_API_KEY", "")
            if api_key:
                error_message = error_message.replace(api_key, "[redacted]")
            logger.warning("send_audio failed: %s: %s", type(exc).__name__, error_message)
            await emit(
                "error",
                code="GEMINI_INPUT_FAILED",
                message="Audio could not be forwarded to Gemini. Please restart the call.",
                recoverable=False,
            )
            await finish("error")
            return False
        finally:
            duration_ms = (time.perf_counter() - send_started) * 1000
            max_send_audio_duration_ms = max(max_send_audio_duration_ms, duration_ms)
            if duration_ms > 250:
                logger.warning("slow send_audio duration_ms=%.2f", duration_ms)
        audio_frames_forwarded += 1
        audio_bytes_forwarded += len(frame)
        if audio_frames_forwarded % 50 == 0:
            await emit("audio_forwarded", frames=audio_frames_forwarded, bytes=audio_bytes_forwarded)
        return True

    cancelled_ids: set[str] = set()
    service = OrderService()
    try:
        async with app.state.session_lock:
            maximum = int(_setting("MAX_CONCURRENT_SESSIONS", "5"))
            if app.state.active_sessions >= maximum:
                await emit("error", code="SESSION_LIMIT", message="Maximum concurrent calls reached.", recoverable=False)
                await websocket.close(code=1013)
                return
            app.state.active_sessions += 1
            acquired = True
        while not ended:
            remaining = (max_duration - (time.monotonic() - started)) if started is not None else idle_timeout
            if started is not None and remaining <= 0:
                await finish("session_limit")
                break
            receive_task = asyncio.create_task(websocket.receive())
            close_task = asyncio.create_task(live_closed.wait()) if event_task is not None else None
            greeting_done_task = (
                asyncio.create_task(greeting_done.wait())
                if greeting_pending and not greeting_done.is_set() else None
            )
            waiters = {receive_task}
            if close_task is not None:
                waiters.add(close_task)
            if greeting_done_task is not None:
                waiters.add(greeting_done_task)
            try:
                done, pending = await asyncio.wait(
                    waiters, timeout=min(idle_timeout, remaining),
                    return_when=asyncio.FIRST_COMPLETED)
            except BaseException:
                for task in waiters:
                    task.cancel()
                await asyncio.gather(*waiters, return_exceptions=True)
                raise
            for task in waiters - done:
                task.cancel()
            if waiters - done:
                await asyncio.gather(*(waiters - done), return_exceptions=True)
            if not done:
                await finish("session_limit" if remaining <= idle_timeout else "session_limit")
                break
            if close_task is not None and close_task in done:
                if not ended:
                    await emit("error", code="GEMINI_UNAVAILABLE", message="The Gemini session closed unexpectedly.", recoverable=True)
                    await finish("error")
                break
            if greeting_done_task is not None and greeting_done_task in done:
                while startup_audio:
                    frame = startup_audio.popleft()
                    if not await forward_audio(frame):
                        break
                if ended:
                    break
                if receive_task not in done:
                    continue
            message = receive_task.result()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                binary_frames_received += 1
                binary_bytes_received += len(message["bytes"])
                if live:
                    if greeting_pending and not greeting_done.is_set():
                        # Hold a bounded startup window without interleaving
                        # realtime audio with send_client_content. End-call
                        # control remains readable by this receive loop.
                        startup_audio.append(message["bytes"])
                        continue
                    while startup_audio:
                        if not await forward_audio(startup_audio.popleft()):
                            break
                    if ended:
                        break
                    await forward_audio(message["bytes"])
                    if ended:
                        break
                continue
            raw = message.get("text")
            try:
                control = json.loads(raw or "")
                if not isinstance(control, dict) or not isinstance(control.get("type"), str):
                    raise ValueError
            except (json.JSONDecodeError, ValueError):
                await emit("error", code="BAD_MESSAGE", message="Expected a JSON control object with a type.", recoverable=True)
                continue
            if control["type"] == "start_call":
                if live:
                    await emit("error", code="SESSION_ACTIVE", message="A call is already active on this socket.", recoverable=True)
                    continue
                key = _setting("GEMINI_API_KEY", "")
                if not key or key == "your-gemini-api-key":
                    await emit("error", code="GEMINI_UNAVAILABLE", message="Gemini API key is not configured on the backend.", recoverable=False)
                    await websocket.close(code=1011)
                    break
                await emit("status", state="connecting")
                try:
                    call_model = _setting("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
                    live = app.state.live_factory(key, call_model)
                    await live.connect()
                    config_field_names = getattr(live, "config_field_names", [
                        "response_modalities", "system_instruction", "tools",
                        "input_audio_transcription", "output_audio_transcription",
                    ])
                    logger.info("websocket call connected model=%s live_config_fields=%s", call_model, config_field_names)
                    started = time.monotonic()
                    live_closed.clear()
                    await emit("status", state="live")
                    greeting_pending = True
                    event_task = asyncio.create_task(provider_events())
                    greeting_task = asyncio.create_task(send_startup_greeting())
                except Exception:
                    await emit("error", code="GEMINI_UNAVAILABLE", message="Could not start the Gemini session.", recoverable=False)
                    await finish("error")
                    break
            elif control["type"] == "end_call":
                await finish("user_ended")
            else:
                await emit("error", code="BAD_MESSAGE", message="Unknown control message.", recoverable=True)
    except WebSocketDisconnect:
        pass
    except Exception:
        if not ended:
            try:
                await emit("error", code="INTERNAL", message="The call ended unexpectedly.", recoverable=True)
                await finish("error")
            except Exception:
                pass
    finally:
        # Release the slot synchronously before any cancellable teardown awaits.
        if acquired:
            app.state.active_sessions = max(0, app.state.active_sessions - 1)
            acquired = False
        logger.info(
            "call summary model=%s config_fields=%s binary_frames_received=%d binary_bytes_received=%d "
            "send_audio_successes=%d send_audio_exceptions=%d max_send_audio_duration_ms=%.2f "
            "provider_events=%d provider_field_counts=%s",
            call_model, config_field_names, binary_frames_received, binary_bytes_received,
            send_audio_successes, send_audio_exceptions, max_send_audio_duration_ms,
            provider_event_count, dict(provider_field_counts),
        )
        # Close the provider session before awaiting a possibly blocked event
        # task, so disconnect cancellation cannot strand the live connection.
        handler_cancelled = False
        if live:
            close_task = asyncio.create_task(live.close())
            try:
                await asyncio.shield(close_task)
            except asyncio.CancelledError:
                # Preserve close completion when the handler itself is cancelled.
                # Cancellation of the child is distinct: the shield keeps it alive.
                handler_cancelled = asyncio.current_task().cancelling() > 0
                try:
                    await asyncio.shield(close_task)
                except asyncio.CancelledError:
                    handler_cancelled = True
            except Exception:
                pass
        if greeting_task is not None and not greeting_task.done():
            greeting_task.cancel()
            await asyncio.gather(greeting_task, return_exceptions=True)
        if event_task is not None and not event_task.done():
            event_task.cancel()
            await asyncio.gather(event_task, return_exceptions=True)
        if ended:
            try:
                await websocket.close()
            except Exception:
                pass
        if handler_cancelled:
            raise asyncio.CancelledError
