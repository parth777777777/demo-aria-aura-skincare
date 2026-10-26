"""Manual-only Gemini Live smoke test; never collected by pytest.

From backend/, with GEMINI_API_KEY configured in .env, run:
    python -m scripts.live_smoke
"""
import asyncio
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.domain.confirmations import PendingActionStore
from app.domain.orders import OrderService
from app.live.session import GeminiLiveSession
from app.tools.registry import execute_tool

PROMPTS = (
    "What's the status of order ORD-103?",
    "Please cancel it.",
    "Yes, I confirm, cancel it.",
    "What's the status of ORD-103 now?",
)


def get(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        result = value.get(name) if isinstance(value, dict) else getattr(value, name, None)
        if result is not None:
            return result
    return default


async def main() -> None:
    async with asyncio.timeout(90):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise SystemExit("Set GEMINI_API_KEY in backend/.env before running this manual test.")
        model = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
        print(f"model: {model}")
        session = GeminiLiveSession(key, model)
        service = OrderService()
        confirmation = PendingActionStore(
            ttl_seconds=int(os.getenv("PENDING_ACTION_TTL_SECONDS", "300"))
        )
        user_turn = 0
        audio_chunks = audio_bytes = output_index = input_index = 0
        try:
            await session.connect()
            for prompt in PROMPTS:
                user_turn += 1
                print(f"--- user turn {user_turn}: {prompt}")
                await session.send_text(prompt)
                async for event in session.events():
                    content = get(event, "server_content", "serverContent")
                    if content:
                        inc = get(content, "input_transcription", "inputTranscription")
                        if inc and get(inc, "text"):
                            input_index += 1
                            print(f"input_transcription[{input_index}]: {get(inc, 'text')!r}")
                        out = get(content, "output_transcription", "outputTranscription")
                        if out and get(out, "text"):
                            output_index += 1
                            print(f"output_transcription[{output_index}]: {get(out, 'text')!r}")
                        model_turn = get(content, "model_turn", "modelTurn")
                        for part in get(model_turn, "parts", default=[]) or []:
                            data = get(get(part, "inline_data", "inlineData"), "data")
                            if data:
                                audio_chunks += 1
                                audio_bytes += len(data)
                        if get(content, "interrupted", default=False):
                            print("interrupted")
                    away = get(event, "go_away", "goAway")
                    if away:
                        print("go_away")
                    toolcall = get(event, "tool_call", "toolCall")
                    for call in get(toolcall, "function_calls", "functionCalls", default=[]) or []:
                        call_id = get(call, "id")
                        name, args = get(call, "name", default=""), get(call, "args", default={})
                        print(f"tool_call: id={call_id!r} name={name!r} args={args!r}")
                        result = execute_tool(service, name, args, confirmation_state=confirmation,
                                              finalized_user_turn=user_turn)
                        code = result.get("error", {}).get("code") if not result.get("ok") else None
                        print(f"tool_result: {'ok' if result.get('ok') else 'error'}{f' code={code}' if code else ''}")
                        await session.send_tool_response(call_id, name, result)
                    if content and get(content, "turn_complete", "turnComplete", default=False):
                        print("turn_complete")
                        break
            print(f"audio: {audio_chunks} chunks, {audio_bytes} bytes")
        except Exception as exc:
            print(f"error: {type(exc).__name__}: {str(exc).replace(key, '***')[:500]}")
            raise
        finally:
            await session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TimeoutError:
        print("error: TimeoutError")
