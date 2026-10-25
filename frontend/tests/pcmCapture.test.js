import test from "node:test";
import assert from "node:assert/strict";
import {
  createFramer,
  createResampler,
  floatToPcm16,
} from "../src/lib/pcmCapture.js";

test("floatToPcm16 clamps, maps endpoints and replaces NaN", () => {
  assert.deepEqual(
    [...floatToPcm16(new Float32Array([0, 1, -1, 2, NaN]))],
    [0, 32767, -32768, 32767, 0],
  );
});
test("framer emits little-endian complete frames and holds remainder", () => {
  const framer = createFramer(320);
  assert.equal(framer.push(new Int16Array(319)).length, 0);
  const frames = framer.push(Int16Array.of(0x1234));
  assert.equal(frames.length, 1);
  assert.equal(frames[0].byteLength, 640);
  assert.equal(new DataView(frames[0]).getUint16(638, true), 0x1234);
});
test("48k resampling has expected length and preserves DC", () => {
  const out = createResampler(48000).process(new Float32Array(4800).fill(0.25));
  assert.ok(Math.abs(out.length - 1600) <= 1);
  assert.ok([...out].every((x) => x === 0.25));
});
test("44.1k resampling is stable over uneven chunks", () => {
  const input = Float32Array.from({ length: 4410 }, (_, i) => Math.sin(i / 31));
  const one = createResampler(44100).process(input);
  const resampler = createResampler(44100);
  const chunks = [
    resampler.process(input.slice(0, 73)),
    resampler.process(input.slice(73, 1761)),
    resampler.process(input.slice(1761)),
  ];
  assert.ok(
    Math.abs(chunks.reduce((n, x) => n + x.length, 0) - one.length) <= 1,
  );
  assert.ok(chunks.flatMap((x) => [...x]).every(Number.isFinite));
});
test("16k resampling passes through identically", () => {
  const input = Float32Array.of(-1, 0, 0.5);
  assert.deepEqual([...createResampler(16000).process(input)], [...input]);
});
