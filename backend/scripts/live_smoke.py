"""Manual Gemini Live smoke test (makes a real API call; never collected by pytest).

Run from backend after setting GEMINI_API_KEY in backend/.env:
    python scripts/live_smoke.py
It opens one session, sends a short text prompt and a brief silent PCM frame,
then prints provider event types. It does not execute business tool calls.
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from app.live.session import GeminiLiveSession


async def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise SystemExit("Set GEMINI_API_KEY in backend/.env before running this manual test.")
    session = GeminiLiveSession(key, os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live"))
    await session.connect()
    try:
        await session.send_text("Hello Aria. Please briefly introduce yourself.")
        await session.send_audio(bytes(16000 * 2 // 5))  # 400 ms silence, PCM16 mono/16 kHz
        async for event in session.events():
            print(type(event).__name__, event)
            if getattr(getattr(event, "server_content", None), "turn_complete", False):
                break
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
