import test from "node:test";
import assert from "node:assert/strict";
import { createCallSocket } from "../src/lib/callSocket.js";

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 3;
  constructor(url) {
    this.url = url;
    this.readyState = FakeWebSocket.CONNECTING;
    this.listeners = {};
    this.sent = [];
    FakeWebSocket.instance = this;
  }
  addEventListener(type, callback) {
    (this.listeners[type] ||= []).push(callback);
  }
  emit(type, data) {
    for (const callback of this.listeners[type] || []) callback({ data });
  }
  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.emit("open");
  }
  send(data) {
    this.sent.push(data);
  }
  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.emit("close");
  }
}

const make = (onAudio = () => {}) => {
  const events = [];
  const client = createCallSocket({
    url: "ws://test/ws/call",
    onEvent: (event) => events.push(event),
    onAudio,
    WebSocketImpl: FakeWebSocket,
  });
  client.start();
  return { client, events, socket: FakeWebSocket.instance };
};
const makeWithPayload = (startPayload) => {
  const events = [];
  const client = createCallSocket({
    url: "ws://test/ws/call",
    startPayload,
    onEvent: (event) => events.push(event),
    WebSocketImpl: FakeWebSocket,
  });
  client.start();
  return { client, events, socket: FakeWebSocket.instance };
};
const sendEvent = (socket, event) =>
  socket.emit("message", JSON.stringify(event));

test("start sends start_call exactly once", () => {
  const { client, events, socket } = make();
  client.start();
  socket.open();
  assert.deepEqual(socket.sent, ['{"type":"start_call"}']);
  assert.deepEqual(events, []);
});

test("account-mode start payload includes its credential", () => {
  const credential = "opaque-secret";
  const { socket } = makeWithPayload({
    type: "start_call",
    mode: "account",
    credential,
  });
  socket.open();
  assert.deepEqual(JSON.parse(socket.sent[0]), {
    type: "start_call",
    mode: "account",
    credential,
  });
});

test("events reach onEvent", () => {
  const { events, socket } = make();
  socket.open();
  const event = { type: "status", state: "live", ts: "now" };
  sendEvent(socket, event);
  assert.deepEqual(events, [event]);
});

test("one call uses one socket and sends start_call once across real statuses", () => {
  const { client, events, socket } = make();
  client.start();
  client.start();
  socket.open();
  sendEvent(socket, { type: "status", state: "connecting" });
  sendEvent(socket, { type: "status", state: "live" });
  client.end();
  sendEvent(socket, { type: "status", state: "ending", reason: "user_ended" });
  sendEvent(socket, { type: "summary", summary: { call_summary: "Done" } });
  sendEvent(socket, { type: "status", state: "ended", reason: "user_ended" });

  assert.equal(socket.url, "ws://test/ws/call");
  assert.deepEqual(socket.sent, [
    '{"type":"start_call"}',
    '{"type":"end_call"}',
  ]);
  assert.deepEqual(
    events.map((event) => (event.type === "status" ? event.state : event.type)),
    ["connecting", "live", "ending", "summary", "ended"],
  );
});

test("malformed JSON is ignored", () => {
  const { events, socket } = make();
  socket.emit("message", "{");
  assert.deepEqual(events, []);
});

test("binary frames are forwarded to onAudio", () => {
  const audio = [];
  const { events, socket } = make((frame) => audio.push(frame));
  const frame = new ArrayBuffer(2);
  socket.emit("message", frame);
  assert.deepEqual(events, []);
  assert.deepEqual(audio, [frame]);
  assert.equal(socket.binaryType, "arraybuffer");
});

test("disposed sockets ignore binary frames", () => {
  const audio = [];
  const { client, socket } = make((frame) => audio.push(frame));
  client.close();
  socket.emit("message", new ArrayBuffer(2));
  assert.deepEqual(audio, []);
});

test("end sends end_call only while open", () => {
  const { client, socket } = make();
  socket.open();
  client.end();
  assert.deepEqual(socket.sent, [
    '{"type":"start_call"}',
    '{"type":"end_call"}',
  ]);
});

test("bare close reports connection lost", () => {
  const { socket, events } = make();
  socket.close();
  assert.deepEqual(events, [{ type: "connection_lost" }]);
});

test("close after ended does not report connection lost", () => {
  const { socket, events } = make();
  const event = { type: "status", state: "ended" };
  sendEvent(socket, event);
  socket.close();
  assert.deepEqual(events, [event]);
});

test("close after fatal error does not report connection lost", () => {
  const { socket, events } = make();
  const event = { type: "error", code: "INTERNAL", recoverable: false };
  sendEvent(socket, event);
  socket.close();
  assert.deepEqual(events, [event]);
});

test("error then close reports exactly one connection_lost", () => {
  const { socket, events } = make();
  socket.emit("error");
  socket.emit("close");
  assert.deepEqual(events, [{ type: "connection_lost" }]);
});

test("close while idle or never started reports no connection_lost", () => {
  const events = [];
  const client = createCallSocket({
    url: "ws://test/ws/call",
    onEvent: (event) => events.push(event),
    WebSocketImpl: FakeWebSocket,
  });
  client.close();
  client.start();
  assert.deepEqual(events, []);
});

test("double start is guarded", () => {
  const { client, socket } = make();
  client.start();
  socket.open();
  assert.equal(socket.sent.length, 1);
});

test("end while connecting closes without sending start_call or connection_lost", () => {
  const { client, events, socket } = make();
  client.end();
  socket.emit("open");
  assert.deepEqual(socket.sent, []);
  assert.equal(socket.readyState, FakeWebSocket.CLOSED);
  assert.deepEqual(events, [{ type: "call_cancelled" }]);
  assert.equal(
    events.some((event) => event.type === "summary"),
    false,
  );
});

test("disposed old socket events and close are ignored after a new socket starts", () => {
  const old = make();
  old.client.close();
  const next = make();
  old.socket.emit("message", JSON.stringify({ type: "status", state: "live" }));
  old.socket.emit("close");
  assert.deepEqual(old.events, []);
  assert.deepEqual(next.events, []);
});
