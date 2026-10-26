import asyncio
import wave
from pathlib import Path

import pytest

from scripts.make_fixture import RATE, resample_pcm, validate_wav
from scripts.ws_audio_smoke import FRAME_BYTES, FRAME_SECONDS, audio_frames, read_wav, send_paced


def test_resample_pcm_doubles_samples():
    assert resample_pcm(b"\x00\x00\xe8\x03", 2, 4) == b"\x00\x00\xf4\x01\xe8\x03\xe8\x03"


def test_validation_accepts_and_rejects_in_memory_wav(tmp_path: Path):
    path = tmp_path / "test.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(b"\0\0" * 100 + b"\xe8\x03" * 100)
    result = validate_wav(path)
    assert result[:3] == (16000, 1, 2)
    assert result[3] == pytest.approx(0.0125)
    assert result[4] == 1000
    assert read_wav(path)
    silent = tmp_path / "silent.wav"
    with wave.open(str(silent), "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(RATE); wav.writeframes(b"\0\0" * 100)
    with pytest.raises(ValueError, match="silent"):
        validate_wav(silent)


def test_audio_frames_are_640_bytes_and_padded():
    frames = audio_frames(b"\x01\x02" * (FRAME_BYTES // 2 + 1))
    assert len(frames[0]) == FRAME_BYTES
    assert len(frames[1]) == 2


def test_send_paced_sends_frames_in_order():
    class Socket:
        sent = []

        async def send(self, frame):
            self.sent.append(frame)

    socket = Socket()
    asyncio.run(send_paced(socket, [b"a" * FRAME_BYTES, b"b" * FRAME_BYTES], FRAME_SECONDS))
    assert socket.sent == [b"a" * FRAME_BYTES, b"b" * FRAME_BYTES]
