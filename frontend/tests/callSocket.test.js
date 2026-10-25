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
  open() { this.readyState = FakeWebSocket.OPEN; this.emit("open"); }
  send(data) { this.sent.push(data); }
  close() { this.readyState = FakeWebSocket.CLOSED; this.emit("close"); }
}

const make = () => {
  const events = [];
  const client = createCallSocket({ url: "ws://test/ws/call", onEvent: (event) => events.push(event), WebSocketImpl: FakeWebSocket });
  client.start();
  return { client, events, socket: FakeWebSocket.instance };
};
const sendEvent = (socket, event) => socket.emit("message", JSON.stringify(event));

test("start sends start_call exactly once", () => {
  const { client, events, socket } = make();
  client.start();
  socket.open();
  assert.deepEqual(socket.sent, ['{"type":"start_call"}']);
  assert.deepEqual(events, []);
});

test("events reach onEvent", () => {
  const { events, socket } = make();
  socket.open();
  const event = { type: "status", state: "live", ts: "now" };
  sendEvent(socket, event);
  assert.deepEqual(events, [event]);
});

test("malformed JSON is ignored", () => {
  const { events, socket } = make();
  socket.emit("message", "{");
  assert.deepEqual(events, []);
});

test("binary frames are ignored", () => {
  const { events, socket } = make();
  socket.emit("message", new ArrayBuffer(2));
  assert.deepEqual(events, []);
});

test("end sends end_call only while open", () => {
  const { client, socket } = make();
  socket.open();
  client.end();
  assert.deepEqual(socket.sent, ['{"type":"start_call"}', '{"type":"end_call"}']);
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
  const client = createCallSocket({ url: "ws://test/ws/call", onEvent: (event) => events.push(event), WebSocketImpl: FakeWebSocket });
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
