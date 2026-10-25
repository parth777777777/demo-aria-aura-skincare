import test from "node:test";
import assert from "node:assert/strict";
import {
  acquireMicThenOpen,
  cleanupMic,
  createFrameGate,
  createStartLock,
  endMicCall,
  MICROPHONE_ERROR,
  onMicTrackEnded,
} from "../src/lib/micLifecycle.js";

function socket(readyState = 1, bufferedAmount = 0) {
  return {
    readyState,
    bufferedAmount,
    sent: [],
    send(frame) {
      this.sent.push(frame);
    },
  };
}

test("mic gate drops frames before live", () => {
  const ws = socket();
  const rejected = [];
  const send = createFrameGate({
    getSocket: () => ws,
    isLive: () => false,
    onRejected: (reason) => rejected.push(reason),
  });
  assert.equal(send("frame"), false);
  assert.deepEqual(ws.sent, []);
  assert.deepEqual(rejected, ["not_live"]);
});
test("mic gate sends frames while live and socket open", () => {
  const ws = socket();
  const send = createFrameGate({ getSocket: () => ws, isLive: () => true });
  assert.equal(send("frame"), true);
  assert.deepEqual(ws.sent, ["frame"]);
});
test("mic gate drops frames when socket is closed", () => {
  const ws = socket(3);
  const rejected = [];
  const send = createFrameGate({
    getSocket: () => ws,
    isLive: () => true,
    onRejected: (reason) => rejected.push(reason),
  });
  assert.equal(send("frame"), false);
  assert.deepEqual(ws.sent, []);
  assert.deepEqual(rejected, ["socket_not_open"]);
});
test("mic gate drops frames above 256 KB backpressure", () => {
  const ws = socket(1, 256 * 1024 + 1);
  const rejected = [];
  const send = createFrameGate({
    getSocket: () => ws,
    isLive: () => true,
    onRejected: (reason, amount) => rejected.push([reason, amount]),
  });
  assert.equal(send("frame"), false);
  assert.deepEqual(ws.sent, []);
  assert.deepEqual(rejected, [["buffered_amount", 256 * 1024 + 1]]);
});
test("permission denial creates no socket, shows fixed error and releases context", async () => {
  let opened = false;
  let shown;
  let closed = 0;
  const context = {
    state: "running",
    close() {
      closed++;
      this.state = "closed";
    },
  };
  const result = await acquireMicThenOpen({
    getUserMedia: async () => {
      throw new Error("denied");
    },
    context,
    loadWorklet: async () => {},
    openSocket: () => {
      opened = true;
    },
    onError: (message) => {
      shown = message;
    },
  });
  assert.equal(result, null);
  assert.equal(opened, false);
  assert.equal(shown, MICROPHONE_ERROR);
  assert.equal(closed, 1);
});
test("worklet load failure creates no socket, shows fixed error and releases context", async () => {
  let opened = false;
  let shown;
  let closed = 0;
  const context = {
    state: "running",
    audioWorklet: {
      async addModule() {
        throw new Error("worklet load failed");
      },
    },
    close() {
      closed++;
      this.state = "closed";
    },
  };
  const result = await acquireMicThenOpen({
    getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }),
    context,
    loadWorklet: (audioContext) =>
      audioContext.audioWorklet.addModule("/mic-worklet.js"),
    openSocket: () => {
      opened = true;
    },
    onError: (message) => {
      shown = message;
    },
  });
  assert.equal(result, null);
  assert.equal(opened, false);
  assert.equal(shown, MICROPHONE_ERROR);
  assert.equal(closed, 1);
});
test("cleanup stops all tracks and disconnects source and worklet nodes", () => {
  let stops = 0;
  let disconnects = 0;
  let portCloses = 0;
  const stream = {
    getTracks: () => [
      {
        stop() {
          stops++;
        },
      },
      {
        stop() {
          stops++;
        },
      },
    ],
  };
  const node = {
    port: {
      onmessage: () => {},
      close() {
        portCloses++;
      },
    },
    disconnect() {
      disconnects++;
    },
  };
  cleanupMic({
    stream,
    source: {
      disconnect() {
        disconnects++;
      },
    },
    node,
  });
  assert.equal(stops, 2);
  assert.equal(disconnects, 2);
  assert.equal(portCloses, 1);
  assert.equal(node.port.onmessage, null);
});
test("track-ended handler uses the normal end path and fixed notice", () => {
  const calls = [];
  const track = {
    ended: null,
    addEventListener(type, handler, options) {
      assert.equal(type, "ended");
      assert.deepEqual(options, { once: true });
      this.ended = handler;
    },
  };
  onMicTrackEnded(track, () => {
    calls.push("notice:Microphone disconnected.");
    endMicCall({
      socket: { end: () => calls.push("end") },
      cleanup: () => calls.push("cleanup"),
    });
  });
  track.ended();
  assert.deepEqual(calls, [
    "notice:Microphone disconnected.",
    "end",
    "cleanup",
  ]);
});
test("start lock prevents concurrent starts opening duplicate streams", async () => {
  const lock = createStartLock();
  let streams = 0;
  let release;
  const pending = new Promise((resolve) => {
    release = resolve;
  });
  const start = () =>
    lock.run(async () => {
      streams++;
      await pending;
    });
  const first = start();
  const second = start();
  await second;
  assert.equal(streams, 1);
  release();
  await first;
});
