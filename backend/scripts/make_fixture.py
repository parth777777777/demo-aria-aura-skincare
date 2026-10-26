"""Generate a short, deterministic spoken order-status WAV fixture."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path

RATE = 16_000
SENTENCE = "What's the status of order O R D one oh one?"
OUTPUT = Path(__file__).resolve().parents[1] / "tests/fixtures/order_status_ord101.wav"
ORDER_ID_FIRST_SENTENCE = "Check order O R D one oh one."
ORDER_ID_FIRST_OUTPUT = Path(__file__).resolve().parents[1] / "tests/fixtures/order_check_ord101.wav"


def resample_pcm(samples: bytes, source_rate: int, target_rate: int) -> bytes:
    """Linearly resample little-endian signed 16-bit mono PCM in memory."""
    if source_rate <= 0 or target_rate <= 0 or len(samples) % 2:
        raise ValueError("invalid PCM data or sample rate")
    source = array("h")
    source.frombytes(samples)
    if __import__("sys").byteorder != "little":
        source.byteswap()
    if not source:
        return b""
    count = max(1, round(len(source) * target_rate / source_rate))
    output = array("h")
    for index in range(count):
        position = index * source_rate / target_rate
        left = min(int(position), len(source) - 1)
        right = min(left + 1, len(source) - 1)
        fraction = position - left
        output.append(round(source[left] * (1 - fraction) + source[right] * fraction))
    if __import__("sys").byteorder != "little":
        output.byteswap()
    return output.tobytes()


def validate_wav(path: Path) -> tuple[int, int, int, float, int]:
    with wave.open(str(path), "rb") as wav:
        rate, channels, width, frames = wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()
        data = wav.readframes(frames)
    if (rate, channels, width) != (RATE, 1, 2):
        raise ValueError(f"unexpected WAV format: {rate} Hz, {channels} ch, {width} bytes/sample")
    values = array("h")
    values.frombytes(data)
    if __import__("sys").byteorder != "little":
        values.byteswap()
    peak = max((abs(value) for value in values), default=0)
    if peak < 100:
        raise ValueError(f"WAV is effectively silent (peak={peak})")
    return rate, channels, width, frames / rate, peak


def generate(output: Path = OUTPUT, sentence: str = SENTENCE) -> tuple[int, int, int, float, int]:
    espeak = shutil.which("espeak-ng")
    if not espeak:
        raise RuntimeError("espeak-ng is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        source_path = Path(temporary) / "speech.wav"
        normalized_path = Path(temporary) / "normalized.wav"
        subprocess.run(
            [espeak, "-v", "en-us", "-s", "160", "-g", "2", "-p", "45", "-w", str(source_path), sentence],
            check=True,
        )
        with wave.open(str(source_path), "rb") as source:
            params = source.getparams()
            frames = source.readframes(source.getnframes())
        if (params.framerate, params.nchannels, params.sampwidth) != (RATE, 1, 2):
            ffmpeg = shutil.which("ffmpeg")
            sox = shutil.which("sox")
            if ffmpeg:
                subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(source_path), "-ar", str(RATE), "-ac", "1", "-sample_fmt", "s16", str(normalized_path)], check=True)
            elif sox:
                subprocess.run([sox, str(source_path), "-r", str(RATE), "-c", "1", "-b", "16", str(normalized_path)], check=True)
            else:
                frames = resample_pcm(frames, params.framerate, RATE)
                with wave.open(str(normalized_path), "wb") as target:
                    target.setnchannels(1); target.setsampwidth(2); target.setframerate(RATE); target.writeframes(frames)
            with wave.open(str(normalized_path), "rb") as normalized:
                frames = normalized.readframes(normalized.getnframes())
        silence = b"\0\0" * (RATE * 300 // 1000)
        with wave.open(str(output), "wb") as target:
            target.setnchannels(1); target.setsampwidth(2); target.setframerate(RATE)
            target.writeframes(silence + frames)
    result = validate_wav(output)
    rate, channels, width, duration, peak = result
    print(f"WAV: {output}")
    print(f"Sentence: {sentence}")
    print(f"Format: {rate} Hz, {channels} channel, {width * 8}-bit PCM")
    print(f"Duration: {duration:.3f} s")
    print(f"PEAK amplitude: {peak}")
    print(f"Size: {output.stat().st_size} bytes")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--order-id-first", action="store_true", help="speak 'Check order O R D one oh one.'")
    args = parser.parse_args()
    output = args.output
    sentence = SENTENCE
    if args.order_id_first:
        if output == OUTPUT:
            output = ORDER_ID_FIRST_OUTPUT
        sentence = ORDER_ID_FIRST_SENTENCE
    generate(output, sentence)
