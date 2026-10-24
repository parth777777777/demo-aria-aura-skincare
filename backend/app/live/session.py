"""Small SDK-facing Gemini Live session adapter."""

from collections.abc import AsyncIterator
from typing import Any

from app.live.prompt import ARIA_SYSTEM_PROMPT
from app.tools.registry import get_tool_definitions


class GeminiLiveSession:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key, self.model = api_key, model
        self._manager: Any = None
        self.session: Any = None

    async def connect(self) -> None:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=self.api_key)
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"], system_instruction=ARIA_SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=get_tool_definitions())],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )
        self._manager = client.aio.live.connect(model=self.model, config=config)
        self.session = await self._manager.__aenter__()

    async def send_audio(self, audio: bytes) -> None:
        await self.session.send_realtime_input(audio=types_blob(audio))

    async def send_text(self, text: str) -> None:
        await self.session.send_client_content(
            turns={"parts": [{"text": text}]}, turn_complete=True)

    async def send_tool_response(self, call_id: str, name: str, result: dict[str, Any]) -> None:
        from google.genai import types
        await self.session.send_tool_response(function_responses=[types.FunctionResponse(
            id=call_id, name=name, response=result)])

    async def events(self) -> AsyncIterator[Any]:
        async for event in self.session.receive():
            yield event

    async def close(self) -> None:
        if self._manager is not None:
            manager, self._manager = self._manager, None
            self.session = None
            await manager.__aexit__(None, None, None)


def types_blob(audio: bytes) -> Any:
    from google.genai import types
    return types.Blob(data=audio, mime_type="audio/pcm;rate=16000")
