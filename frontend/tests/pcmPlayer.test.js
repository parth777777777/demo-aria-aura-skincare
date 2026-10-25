import test from "node:test";
import assert from "node:assert/strict";
import { createPcmPlayer } from "../src/lib/pcmPlayer.js";

class FakeBuffer {
  constructor(channels, length, sampleRate) {
    this.duration = length / sampleRate;
    this.sampleRate = sampleRate;
    this.samples = new Float32Array(length);
  }
  copyToChannel(data) {
    this.samples.set(data);
  }
}
class FakeSource {
  constructor() {
    this.listeners = {};
    this.stops = 0;
  }
  connect() {}
  addEventListener(name, callback) {
    this.listeners[name] = callback;
  }
  start(time) {
    this.startTime = time;
  }
  stop() {
    this.stops++;
  }
}
class FakeContext {
  currentTime = 2;
  state = "running";
  destination = {};
  sources = [];
  createBuffer(...args) {
    return new FakeBuffer(...args);
  }
  createBufferSource() {
    const source = new FakeSource();
    this.sources.push(source);
    return source;
  }
  close() {
    this.state = "closed";
    return Promise.resolve();
  }
}
const pcm = (...samples) => {
  const buffer = new ArrayBuffer(samples.length * 2);
  const view = new DataView(buffer);
  samples.forEach((sample, i) => view.setInt16(i * 2, sample, true));
  return buffer;
};
const setup = () => {
  const context = new FakeContext();
  return { context, player: createPcmPlayer(context) };
};

test("converts Int16 samples 0, 32767, and -32768 to Float32", () => {
  const { context, player } = setup();
  player.enqueue(pcm(0, 32767, -32768));
  assert.deepEqual(
    [...context.sources[0].buffer.samples],
    [0, 32767 / 32768, -1],
  );
  assert.equal(context.sources[0].buffer.sampleRate, 24000);
});

test("carries an odd-length chunk byte across enqueue calls", () => {
  const { context, player } = setup();
  const sample = pcm(1234);
  player.enqueue(sample.slice(0, 1));
  assert.equal(context.sources.length, 0);
  player.enqueue(sample.slice(1));
  assert.deepEqual([...context.sources[0].buffer.samples], [1234 / 32768]);
});

test("ignores an empty chunk", () => {
  const { context, player } = setup();
  player.enqueue(new ArrayBuffer(0));
  assert.equal(context.sources.length, 0);
});

test("schedules back-to-back chunks without a gap", () => {
  const { context, player } = setup();
  player.enqueue(pcm(1, 2));
  player.enqueue(pcm(3, 4, 5));
  const [first, second] = context.sources;
  assert.equal(second.startTime, first.startTime + first.buffer.duration);
});

test("flush stops every active source and resets scheduling", () => {
  const { context, player } = setup();
  player.enqueue(pcm(1));
  player.enqueue(pcm(2));
  player.flush();
  assert.deepEqual(
    context.sources.map((source) => source.stops),
    [1, 1],
  );
  context.currentTime = 7;
  player.enqueue(pcm(3));
  assert.equal(context.sources[2].startTime, 7.05);
});

test("enqueue after flush schedules from currentTime", () => {
  const { context, player } = setup();
  player.enqueue(pcm(1));
  player.flush();
  context.currentTime = 9;
  player.enqueue(pcm(2));
  assert.equal(context.sources[1].startTime, 9.05);
});

test("close can be called twice safely", async () => {
  const { context, player } = setup();
  await player.close();
  await player.close();
  assert.equal(context.state, "closed");
});
