"""Real-Gemini in-process intro/conversation/order lookup smoke test.

Each run uses real Gemini API quota (one short session). Run from backend with
GEMINI_API_KEY configured in backend/.env: python -m scripts.intro_convo_smoke
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.data.orders import ORDERS_FILE
from app.domain.orders import OrderService
from app.live.session import GeminiLiveSession
from app.tools.registry import execute_tool

INTRO_TRIGGER = "The customer just connected. Greet them and introduce yourself briefly."
CUSTOMER_TURNS = (
    "Hi, I just have a couple of quick questions.",
    "How long does delivery usually take?",
    "Is delivery free?",
    "Can I pay cash on delivery?",
    "Can you check where my order ORD-101 is?",
)
TURN_TIMEOUT_SECONDS = 30
MIN_INTRO_AUDIO_BYTES = 100


def build_turn_sequence(order_id: str) -> list[tuple[str, str]]:
    return [("customer", prompt) for prompt in (*CUSTOMER_TURNS[:4], f"Can you check where my order {order_id} is?")]


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def result_matches_order(result: Any, order: dict[str, Any]) -> bool:
    if not isinstance(result, dict) or result.get("ok") is not True:
        return False
    actual = result.get("order")
    if not isinstance(actual, dict):
        return False
    fields = ("status", "total_inr", "items", *(key for key in ("carrier", "tracking_number") if key in order))
    return all(actual.get(key) == order.get(key) for key in fields)


def turn_is_complete(event: Any) -> bool:
    content = get(event, "server_content", "serverContent")
    return bool(content and get(content, "turn_complete", "turnComplete", default=False))


def json_order(path: Path, order_id: str) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        records = json.load(source)
    order = next((record for record in records if record.get("order_id") == order_id), None)
    if order is None:
        raise ValueError(f"Required order {order_id} is missing from {path}")
    return order


def get(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        result = value.get(name) if isinstance(value, dict) else getattr(value, name, None)
        if result is not None:
            return result
    return default


async def run() -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("Set GEMINI_API_KEY in backend/.env before running this real-Gemini test.")
        return 1
    order = json_order(ORDERS_FILE, "ORD-101")
    before = hash_file(ORDERS_FILE)
    model = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
    live = GeminiLiveSession(key, model)
    service = OrderService()
    confirmation: dict[tuple[str, str], int] = {}
    failures: list[str] = []
    finalized_user_turn = 0
    events = live.events()

    async def turn(label: str, prompt: str, *, user_turn: int) -> dict[str, Any]:
        started = time.monotonic()
        texts: list[str] = []
        chunks = byte_count = 0
        calls: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        await live.send_text(prompt)
        async with asyncio.timeout(TURN_TIMEOUT_SECONDS):
            async for event in events:
                content = get(event, "server_content", "serverContent")
                out = get(content, "output_transcription", "outputTranscription") if content else None
                text = get(out, "text") if out else None
                if text:
                    texts.append(text)
                model_turn = get(content, "model_turn", "modelTurn") if content else None
                for part in get(model_turn, "parts", default=[]) or []:
                    audio = get(get(part, "inline_data", "inlineData"), "data")
                    if audio:
                        chunks += 1
                        byte_count += len(audio)
                tool_call = get(event, "tool_call", "toolCall")
                for call in get(tool_call, "function_calls", "functionCalls", default=[]) or []:
                    call_id = get(call, "id")
                    name, args = get(call, "name", default=""), get(call, "args", default={})
                    entry = {"name": name, "args": args}
                    calls.append(entry)
                    result = execute_tool(service, name, args, confirmation_state=confirmation,
                                          finalized_user_turn=user_turn)
                    results.append({"name": name, "args": args, "result": result})
                    await live.send_tool_response(call_id, name, result)
                if turn_is_complete(event):
                    break
        elapsed = time.monotonic() - started
        reply = "".join(texts)
        print(f"{label} transcription: {reply!r}")
        print(f"{label} audio: {chunks} chunks, {byte_count} bytes")
        print(f"{label} tool events: calls={calls!r} results={results!r}")
        print(f"{label} turn_complete: True; duration: {elapsed:.2f}s")
        return {"reply": reply, "chunks": chunks, "bytes": byte_count, "calls": calls, "results": results}

    try:
        await live.connect()
        print(f"model: {model}")
        print(f"TEST-ONLY trigger (not a customer turn): {INTRO_TRIGGER!r}")
        intro = await turn("intro", INTRO_TRIGGER, user_turn=0)
        if not intro["reply"].strip():
            failures.append("intro transcription was empty")
        if intro["bytes"] <= MIN_INTRO_AUDIO_BYTES:
            failures.append(f"intro audio did not exceed {MIN_INTRO_AUDIO_BYTES} bytes")
        if intro["calls"]:
            failures.append(f"intro unexpectedly called tools: {intro['calls']!r}")
        sequence = build_turn_sequence(order["order_id"])
        final_details = None
        for index, (role, prompt) in enumerate(sequence, 1):
            finalized_user_turn += 1
            try:
                outcome = await turn(f"turn {index}", prompt, user_turn=finalized_user_turn)
                if index < len(sequence):
                    if not outcome["reply"].strip():
                        failures.append(f"turn {index} reply was empty")
                    if outcome["calls"]:
                        failures.append(f"turn {index} unexpectedly called tools: {outcome['calls']!r}")
                else:
                    final_details = outcome
            except Exception as exc:
                failures.append(f"turn {index} failed: {type(exc).__name__}")
                print(f"turn {index} failure: {type(exc).__name__}")
        if final_details:
            matching = [item for item in final_details["results"]
                        if item["name"] == "get_order_details" and item["args"].get("order_id") == order["order_id"]]
            if not matching:
                failures.append(f"final turn did not call get_order_details for {order['order_id']}")
            elif not result_matches_order(matching[-1]["result"], order):
                failures.append("final get_order_details result did not match independently loaded JSON")
            final_text = final_details["reply"].casefold()
            amount_match = re.search(r"\d[\d,]*", str(order["total_inr"]))
            print(f"SOFT final transcript mentions status: {order['status'].casefold() in final_text}")
            print(f"SOFT final transcript mentions amount: {bool(amount_match and amount_match.group() in final_text)}")
        after = hash_file(ORDERS_FILE)
        print(f"orders JSON sha256 before: {before}")
        print(f"orders JSON sha256 after:  {after}")
        if before != after:
            failures.append("orders JSON file hash changed during session")
    except Exception as exc:
        failures.append(f"session failed: {type(exc).__name__}")
        print(f"session failure: {type(exc).__name__}")
    finally:
        # Never send an end/close signal after any assertion or run failure.
        if not failures:
            await live.close()
    print(f"exit conditions failed: {failures if failures else 'none'}")
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Uses real Gemini API quota (one short session per run).")
    parser.parse_args()
    try:
        return asyncio.run(run())
    except Exception as exc:
        print(f"smoke test failed: {type(exc).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
