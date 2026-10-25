"""Aura HTTP health endpoint and isolated per-connection call transport."""
import asyncio
import json
import os
import time
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
    live_closed = asyncio.Event()
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
        nonlocal output_turn, output_text, user_turn
        provider_event_count = 0
        async for event in live.events():
            if ended:
                return
            provider_event_count += 1
            if provider_event_count == 1:
                await emit("provider_activity")
            cancellation = _get(event, "tool_call_cancellation", "toolCallCancellation")
            cancelled = _get(cancellation, "ids", default=[]) or [] if cancellation else []
            cancelled_ids.update(cancelled)
            content = _get(event, "server_content", "serverContent")
            if content:
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
            waiters = {receive_task}
            if close_task is not None:
                waiters.add(close_task)
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
            message = receive_task.result()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                if live:
                    try:
                        await live.send_audio(message["bytes"])
                    except Exception:
                        await emit(
                            "error",
                            code="GEMINI_INPUT_FAILED",
                            message="Audio could not be forwarded to Gemini. Please restart the call.",
                            recoverable=False,
                        )
                        await finish("error")
                        break
                    audio_frames_forwarded += 1
                    audio_bytes_forwarded += len(message["bytes"])
                    if audio_frames_forwarded % 50 == 0:
                        await emit("audio_forwarded", frames=audio_frames_forwarded, bytes=audio_bytes_forwarded)
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
                    live = app.state.live_factory(key, _setting("GEMINI_LIVE_MODEL", "gemini-3.8-live"))
                    await live.connect()
                    started = time.monotonic()
                    live_closed.clear()
                    await emit("status", state="live")
                    event_task = asyncio.create_task(provider_events())
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
        if event_task is not None and not event_task.done():
            event_task.cancel()
            await asyncio.gather(event_task, return_exceptions=True)
        if ended:
            try:
                await websocket.close()
            except Exception:
                pass
        if live:
            try:
                await live.close()
            except Exception:
                pass
        if acquired:
            async with app.state.session_lock:
                app.state.active_sessions = max(0, app.state.active_sessions - 1)
