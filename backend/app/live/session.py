"""Small SDK-facing Gemini Live session adapter."""

from collections.abc import AsyncIterator
import logging
from typing import Any

from app.live.prompt import ARIA_SYSTEM_PROMPT
from app.tools.registry import get_tool_definitions

logger = logging.getLogger(__name__)


_SUPPORTED_SCHEMA_KEYS = frozenset({
    "type", "description", "properties", "required", "items", "enum",
    "minimum", "maximum", "minItems", "maxItems", "nullable", "format",
})


def _sanitize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Copy a registry schema into the JSON Schema subset accepted by Live."""
    sanitized: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in _SUPPORTED_SCHEMA_KEYS:
            continue
        if key == "properties":
            sanitized[key] = {name: _sanitize_schema(child) for name, child in value.items()}
        elif key == "items":
            sanitized[key] = _sanitize_schema(value)
        else:
            sanitized[key] = value
    return sanitized


def get_gemini_tool_declarations() -> list[dict[str, Any]]:
    """Return sanitized copies; registry schemas remain strict and unchanged."""
    declarations = get_tool_definitions()
    for declaration in declarations:
        declaration["parameters"] = _sanitize_schema(declaration["parameters"])
    return declarations


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
            tools=[types.Tool(function_declarations=get_gemini_tool_declarations())],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )
        self.config_field_names = [
            "response_modalities", "system_instruction", "tools",
            "input_audio_transcription", "output_audio_transcription",
        ]
        self._manager = client.aio.live.connect(model=self.model, config=config)
        self.session = await self._manager.__aenter__()

    async def send_audio(self, audio: bytes) -> None:
        await self.session.send_realtime_input(audio=types_blob(audio))

    async def send_text(self, text: str) -> None:
        await self.session.send_client_content(
            turns={"role": "user", "parts": [{"text": text}]}, turn_complete=True)

    async def send_tool_response(self, call_id: str, name: str, result: dict[str, Any]) -> None:
        from google.genai import types
        await self.session.send_tool_response(function_responses=[types.FunctionResponse(
            id=call_id, name=name, response=result)])

    async def events(self) -> AsyncIterator[Any]:
        # receive() yields one complete interaction, then returns. Keep the
        # session alive by starting another receive cycle for the next turn.
        try:
            while True:
                received = False
                async for event in self.session.receive():
                    received = True
                    yield event
                if not received:
                    raise RuntimeError("Gemini receive stream ended without an interaction")
        except BaseException as exc:
            logger.info("Gemini events raised: %s", type(exc).__name__)
            raise
        finally:
            logger.info("Gemini events iterator ended")

    async def close(self) -> None:
        if self._manager is not None:
            manager, self._manager = self._manager, None
            self.session = None
            await manager.__aexit__(None, None, None)


def types_blob(audio: bytes) -> Any:
    from google.genai import types
    return types.Blob(data=audio, mime_type="audio/pcm;rate=16000")
