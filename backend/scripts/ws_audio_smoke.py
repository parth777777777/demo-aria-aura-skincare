"""Real Gemini WebSocket smoke test. Each run consumes API quota."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import wave
from collections import Counter
from pathlib import Path
from typing import Any

from websockets.asyncio.client import connect

from scripts.make_fixture import generate

DEFAULT_WAV = Path(__file__).resolve().parents[1] / "tests/fixtures/order_status_ord101.wav"
FRAME_BYTES = 640
FRAME_SECONDS = 0.020


def read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            raise ValueError("WAV must be 16000 Hz, mono, 16-bit PCM")
        return wav.readframes(wav.getnframes())


def audio_frames(pcm: bytes) -> list[bytes]:
    if len(pcm) % 2:
        raise ValueError("PCM byte count must be even")
    return [pcm[i:i + FRAME_BYTES] for i in range(0, len(pcm), FRAME_BYTES)]


async def send_paced(socket: Any, frames: list[bytes], frame_seconds: float = FRAME_SECONDS) -> None:
    deadline = time.monotonic()
    for frame in frames:
        await socket.send(frame.ljust(FRAME_BYTES, b"\0"))
        deadline += frame_seconds
        await asyncio.sleep(max(0, deadline - time.monotonic()))


async def collect_until(socket: Any, predicate: Any, timeout: float, record: list[dict[str, Any]]) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            message = await socket.recv()
            if isinstance(message, bytes):
                record.append({"type": "_audio", "bytes": len(message)})
            else:
                record.append(json.loads(message))


async def run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    if not args.wav.is_file():
        print(f"Fixture missing; generating: {args.wav}")
        generate(args.wav)
    events: list[dict[str, Any]] = []
    failures: list[str] = []
    live = False
    completed = False
    frames_sent = 0
    async with connect(args.url, additional_headers={"Origin": args.origin}, max_size=None) as socket:
        await socket.send(json.dumps({"type": "start_call"}))
        await collect_until(socket, lambda: any(e.get("type") == "status" and e.get("state") == "live" for e in events), args.turn_timeout_s, events)
        live = any(e.get("type") == "status" and e.get("state") == "live" for e in events)
        if live:
            speech_frames = audio_frames(read_wav(args.wav))
            await send_paced(socket, speech_frames)
            frames_sent += len(speech_frames)
            silence_frames = round(args.silence_ms / 1000 / FRAME_SECONDS)
            await send_paced(socket, [b"\0" * FRAME_BYTES] * silence_frames)
            frames_sent += silence_frames
            try:
                await collect_until(socket, lambda: any(e.get("type") == "transcript" and e.get("role") == "aria" and e.get("final") for e in events), args.turn_timeout_s, events)
                completed = True
            except TimeoutError:
                pass
            end_call_event_index = len(events)
            await socket.send(json.dumps({"type": "end_call"}))
            try:
                await collect_until(socket, lambda: any(e.get("type") == "status" and e.get("state") == "ended" for e in events), min(args.turn_timeout_s, 10), events)
            except (TimeoutError, Exception) as exc:
                if not isinstance(exc, (TimeoutError,)):
                    print(f"receive after end_call: {type(exc).__name__}")
    counts = Counter(event.get("type", "unknown") for event in events)
    event_order = [event.get("type", "unknown") for event in events]
    calls = [event for event in events if event.get("type") == "tool_call"]
    results = [event for event in events if event.get("type") == "tool_result"]
    order_call = any(call.get("name") == "get_order_details" and call.get("args", {}).get("order_id") == args.expect_order for call in calls)
    audio_bytes = sum(event.get("bytes", 0) for event in events if event.get("type") == "_audio")
    types = set(event_order)
    summary_after_end = any(
        event.get("type") == "summary" or (event.get("type") == "status" and event.get("state") == "ended")
        for event in events[end_call_event_index:]
    ) if live else False
    if not live: failures.append("status live was not seen")
    if not order_call: failures.append(f"get_order_details tool_call for {args.expect_order} was not seen")
    if audio_bytes <= 1000: failures.append(f"server audio bytes did not exceed 1000 (got {audio_bytes})")
    if not summary_after_end: failures.append("summary or ended event after end_call was not seen")
    print(f"event types: {event_order}")
    print(f"event counts: {dict(counts)}")
    print(f"provider_activity: {'provider_activity' in types}")
    print(f"audio_forwarded: {'audio_forwarded' in types}")
    print(f"input audio frames sent: {frames_sent}")
    print(f"input transcript texts: {[event.get('text') for event in events if event.get('type') == 'transcript' and event.get('role') == 'user']}")
    for event in events:
        if event.get("type") == "transcript":
            print(f"transcript {event.get('role')} final={event.get('final')}: {event.get('text')}")
    for event in calls:
        print(f"tool_call: name={event.get('name')} args={event.get('args')}")
    for event in results:
        print(f"tool_result: name={event.get('name')} result={event.get('result')}")
    print(f"server audio bytes: {audio_bytes}")
    summaries = [event.get("summary") for event in events if event.get("type") == "summary"]
    print(f"summary resolution: {[s.get('resolution_status') for s in summaries if isinstance(s, dict)]}")
    print(f"reply completed: {completed}")
    print(f"duration: {time.monotonic() - started:.2f} s")
    print(f"exit conditions failed: {failures if failures else 'none'}")
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Uses real Gemini API quota (one short session per run).")
    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws/call")
    parser.add_argument("--wav", type=Path, default=DEFAULT_WAV)
    parser.add_argument("--expect-order", default="ORD-101")
    parser.add_argument("--silence-ms", type=int, default=1500)
    parser.add_argument("--turn-timeout-s", type=float, default=25)
    parser.add_argument("--origin", default="http://localhost:5173")
    args = parser.parse_args()
    if args.silence_ms < 0 or args.turn_timeout_s <= 0:
        parser.error("silence-ms must be nonnegative and turn-timeout-s must be positive")
    try:
        return asyncio.run(run(args))
    except Exception as exc:
        print(f"smoke test failed: {type(exc).__name__}: {exc}")
        print("exit conditions failed: WebSocket session did not complete")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
