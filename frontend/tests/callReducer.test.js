import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { callReducer, initialCallState } from "../src/state/callReducer.js";
import { selectVoiceState } from "../src/state/selectors.js";

const mockScenarios = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../src/mocks/call-events.json", import.meta.url)),
    "utf8",
  ),
);

const apply = (events, state = initialCallState) =>
  events.reduce(callReducer, state);
const transcript = (turn_id, role, text, final) => ({
  type: "transcript",
  turn_id,
  role,
  text,
  final,
});
const liveState = () =>
  callReducer(initialCallState, { type: "status", state: "live" });

test("transcript turns are replaced by turn_id for both roles", () => {
  const state = apply([
    transcript("u1", "user", "first", false),
    transcript("a1", "aria", "first", false),
    transcript("u1", "user", "replacement", false),
    transcript("a1", "aria", "replacement", false),
  ]);
  assert.equal(state.turns.length, 2);
  assert.equal(state.turns[0].text, "replacement");
  assert.equal(state.turns[1].text, "replacement");
});

test("a partial transcript is replaced by its final transcript", () => {
  const state = apply([
    transcript("t1", "aria", "Hel", false),
    transcript("t1", "aria", "Hello", true),
  ]);
  assert.deepEqual(state.turns[0], {
    turn_id: "t1",
    role: "aria",
    text: "Hello",
    final: true,
  });
});

test("a late partial transcript cannot overwrite a final turn", () => {
  const state = apply([
    transcript("t1", "user", "Complete", true),
    transcript("t1", "user", "late partial", false),
  ]);
  assert.equal(state.turns[0].text, "Complete");
  assert.equal(state.turns[0].final, true);
});

test("tool_call and tool_result pair by call_id", () => {
  const state = apply([
    { type: "tool_call", call_id: "c1", name: "lookup", args: {} },
    {
      type: "tool_result",
      call_id: "c1",
      name: "lookup",
      result: { ok: true },
    },
  ]);
  assert.equal(state.tools.length, 1);
  assert.deepEqual(state.tools[0].result, { ok: true });
});

test("tool_result arriving before tool_call is retained without crashing", () => {
  const result = { ok: true };
  const state = apply([
    { type: "tool_result", call_id: "c1", result },
    { type: "tool_call", call_id: "c1", name: "lookup", args: {} },
  ]);
  assert.equal(state.tools.length, 1);
  assert.deepEqual(state.tools[0].result, result);
});

test("duplicate tool_result does not duplicate the call entry", () => {
  const state = apply([
    { type: "tool_call", call_id: "c1" },
    { type: "tool_result", call_id: "c1", result: { ok: true } },
    {
      type: "tool_result",
      call_id: "c1",
      result: { ok: true, repeated: true },
    },
  ]);
  assert.equal(state.tools.length, 1);
  assert.deepEqual(state.tools[0].result, { ok: true, repeated: true });
});

test("confirmation identifiers are not retained in tool activity state", () => {
  const state = apply([
    {
      type: "tool_call",
      call_id: "c1",
      name: "cancel_order",
      args: { order_id: "ORD-101", confirmation_id: "secret-args" },
    },
    {
      type: "tool_result",
      call_id: "c1",
      name: "cancel_order",
      result: {
        ok: false,
        error: { code: "CONFIRMATION_REQUIRED" },
        confirmation: { id: "secret-result", action: "cancel_order" },
      },
    },
  ]);
  assert.deepEqual(state.tools[0].args, { order_id: "ORD-101" });
  assert.deepEqual(state.tools[0].result.confirmation, {
    action: "cancel_order",
  });
  assert.equal(JSON.stringify(state).includes("secret-"), false);
});

test("only successful mutation tool results are recorded as successful", () => {
  const state = apply([
    { type: "tool_call", call_id: "pending", name: "cancel_order" },
    {
      type: "tool_result",
      call_id: "pending",
      name: "cancel_order",
      result: { ok: false, error: { code: "CONFIRMATION_REQUIRED" } },
    },
    { type: "tool_call", call_id: "done", name: "cancel_order" },
    {
      type: "tool_result",
      call_id: "done",
      name: "cancel_order",
      result: { ok: true, order_id: "ORD-101" },
    },
  ]);
  assert.equal(state.tools[0].result.ok, false);
  assert.equal(state.tools[1].result.ok, true);
});

test("interrupted finalizes the latest Aria turn and marks it interrupted", () => {
  const state = apply([
    transcript("a1", "aria", "Speaking", false),
    { type: "interrupted" },
  ]);
  assert.equal(state.turns[0].final, true);
  assert.equal(state.turns[0].interrupted, true);
  assert.equal(state.interrupted, true);
});

test("interrupted does not mark a final latest Aria turn interrupted", () => {
  const state = apply([
    transcript("a1", "aria", "Complete", true),
    { type: "interrupted" },
  ]);
  assert.equal(state.turns[0].final, true);
  assert.equal(state.turns[0].interrupted, undefined);
  assert.equal(state.interrupted, false);
});

test("interrupted does not mark state when no Aria turn exists", () => {
  const state = callReducer(initialCallState, { type: "interrupted" });
  assert.equal(state.interrupted, false);
});

for (const reason of ["user_ended", "session_limit", "error"]) {
  test(`ended status preserves the ${reason} reason`, () => {
    const state = callReducer(initialCallState, {
      type: "status",
      state: "ended",
      reason,
    });
    assert.equal(state.status.reason, reason);
    assert.equal(selectVoiceState(state), "ended");
  });
}

test("unknown event types are ignored", () => {
  assert.equal(
    callReducer(initialCallState, { type: "future_event" }),
    initialCallState,
  );
});

test("summary event is stored", () => {
  const summary = {
    customer_intent: "cancellation",
    order_id: "ORD-103",
    resolution_status: "resolved",
    call_summary: "Done",
  };
  assert.deepEqual(
    callReducer(initialCallState, { type: "summary", summary }).summary,
    summary,
  );
});

test("call_requested and reset after ended clear prior call state", () => {
  const ended = apply([
    { type: "status", state: "live" },
    transcript("a1", "aria", "Hi", true),
    { type: "tool_call", call_id: "c1" },
    { type: "error", code: "INTERNAL", message: "failed", recoverable: false },
    { type: "summary", summary: { call_summary: "old" } },
    { type: "status", state: "ended", reason: "error" },
  ]);
  const requested = callReducer(ended, { type: "call_requested" });
  assert.equal(selectVoiceState(requested), "connecting");
  assert.deepEqual(requested.turns, []);
  assert.deepEqual(requested.tools, []);
  assert.equal(requested.summary, null);
  assert.equal(requested.error, null);
  assert.deepEqual(callReducer(ended, { type: "reset" }), initialCallState);
});

test("reducer does not mutate deeply frozen input state", () => {
  const state = Object.freeze({
    status: Object.freeze({ state: "live", reason: null }),
    turns: Object.freeze([
      Object.freeze({ turn_id: "a1", role: "aria", text: "Hi", final: false }),
    ]),
    tools: Object.freeze([Object.freeze({ call_id: "c1", result: null })]),
    summary: null,
    error: null,
    interrupted: false,
  });
  assert.doesNotThrow(() => callReducer(state, { type: "interrupted" }));
  assert.equal(state.turns[0].final, false);
  assert.equal(state.interrupted, false);
});

test("recoverable error is stored without changing call status", () => {
  const state = callReducer(liveState(), {
    type: "error",
    code: "BAD_MESSAGE",
    message: "Malformed",
    recoverable: true,
  });
  assert.equal(state.status.state, "live");
  assert.equal(state.error.recoverable, true);
});

test("non-recoverable error sets call status to error", () => {
  const state = callReducer(liveState(), {
    type: "error",
    code: "SESSION_LIMIT",
    message: "Full",
    recoverable: false,
  });
  assert.deepEqual(state.status, { state: "error", reason: "error" });
  assert.equal(selectVoiceState(state), "error");
});

test("connection_lost is a fixed, non-recoverable error", () => {
  const state = callReducer(liveState(), { type: "connection_lost" });
  assert.deepEqual(state.status, { state: "error", reason: "error" });
  assert.deepEqual(state.error, {
    code: "CONNECTION_LOST",
    message: "Connection lost. Please try again.",
    recoverable: false,
  });
});

test("call_cancelled returns a connecting call to idle", () => {
  const connecting = callReducer(initialCallState, { type: "call_requested" });
  const state = callReducer(connecting, { type: "call_cancelled" });
  assert.deepEqual(state.status, { state: "idle", reason: null });
});

test("startup failure can return to idle while preserving its permission error", () => {
  const state = apply([
    { type: "call_requested" },
    {
      type: "error",
      code: "MICROPHONE_REQUIRED",
      message: "Microphone access is needed.",
      recoverable: true,
    },
    { type: "call_cancelled" },
  ]);
  assert.deepEqual(state.status, { state: "idle", reason: null });
  assert.equal(state.error.message, "Microphone access is needed.");
});

test("selector returns idle", () =>
  assert.equal(selectVoiceState(initialCallState), "idle"));
test("selector returns connecting", () =>
  assert.equal(
    selectVoiceState(
      callReducer(initialCallState, { type: "status", state: "connecting" }),
    ),
    "connecting",
  ));
test("selector returns listening", () =>
  assert.equal(selectVoiceState(liveState()), "listening"));
test("final user transcript selects thinking until Aria starts responding", () => {
  const waiting = callReducer(
    liveState(),
    transcript("u1", "user", "Where is my order?", true),
  );
  assert.equal(selectVoiceState(waiting), "thinking");
  const responding = callReducer(
    waiting,
    transcript("a1", "aria", "I can check that.", false),
  );
  assert.equal(selectVoiceState(responding), "speaking");
});
test("audio forwarding acknowledgments and provider activity are recorded", () => {
  const state = apply([
    { type: "audio_forwarded", frames: 50, bytes: 32000 },
    { type: "provider_activity" },
  ]);
  assert.deepEqual(state.audioForwarded, { frames: 50, bytes: 32000 });
  assert.equal(state.providerActivity, true);
});
test("selector returns thinking for a pending tool call", () =>
  assert.equal(
    selectVoiceState(
      callReducer(liveState(), { type: "tool_call", call_id: "c1" }),
    ),
    "thinking",
  ));
test("selector returns speaking for a non-final Aria turn", () =>
  assert.equal(
    selectVoiceState(
      callReducer(liveState(), transcript("a1", "aria", "Hello", false)),
    ),
    "speaking",
  ));
test("selector returns ended", () =>
  assert.equal(
    selectVoiceState(
      callReducer(initialCallState, { type: "status", state: "ended" }),
    ),
    "ended",
  ));
test("selector returns error", () =>
  assert.equal(
    selectVoiceState(
      callReducer(initialCallState, { type: "status", state: "error" }),
    ),
    "error",
  ));

test("ended takes precedence over a pending tool call", () => {
  const state = apply([
    { type: "status", state: "ended" },
    { type: "tool_call", call_id: "c1" },
  ]);
  assert.equal(selectVoiceState(state), "ended");
});

test("fatal error takes precedence over thinking", () => {
  const state = apply([
    { type: "status", state: "live" },
    { type: "tool_call", call_id: "c1" },
    { type: "error", code: "INTERNAL", message: "failed", recoverable: false },
  ]);
  assert.equal(selectVoiceState(state), "error");
});

test("recoverable error preserves the active voice state", () => {
  const state = apply([
    { type: "status", state: "live" },
    {
      type: "error",
      code: "BAD_MESSAGE",
      message: "Temporary issue",
      recoverable: true,
    },
  ]);
  assert.equal(state.status.state, "live");
  assert.equal(selectVoiceState(state), "listening");
});

test("live pending tool call and partial Aria turn selects thinking", () => {
  const state = apply([
    { type: "status", state: "live" },
    { type: "tool_call", call_id: "c1" },
    transcript("a1", "aria", "One moment", false),
  ]);
  assert.equal(selectVoiceState(state), "thinking");
});

test("thinking clears when the matching tool_result arrives", () => {
  const pending = callReducer(liveState(), {
    type: "tool_call",
    call_id: "c1",
  });
  const resolved = callReducer(pending, {
    type: "tool_result",
    call_id: "c1",
    result: { ok: true },
  });
  assert.equal(selectVoiceState(pending), "thinking");
  assert.equal(selectVoiceState(resolved), "listening");
});

const scenarioExpectations = {
  cancel: { voice: "ended", turns: 4, summary: true, reason: "user_ended" },
  lookup: { voice: "ended", turns: 2, summary: true, reason: "user_ended" },
  error: {
    voice: "error",
    turns: 0,
    summary: false,
    reason: "error",
    recoverable: true,
    status: "error",
  },
  session_limit: {
    voice: "ended",
    turns: 0,
    summary: true,
    reason: "session_limit",
  },
  session_limit_without_summary: {
    voice: "ended",
    turns: 0,
    summary: false,
    reason: "session_limit",
  },
  fatal_error: {
    voice: "error",
    turns: 0,
    summary: false,
    reason: "error",
    recoverable: false,
    status: "error",
  },
  recoverable_error: {
    voice: "listening",
    turns: 0,
    summary: false,
    reason: null,
    recoverable: true,
    status: "live",
  },
  user_ended_no_summary: {
    voice: "ended",
    turns: 0,
    summary: false,
    reason: "user_ended",
  },
};

for (const [name, expected] of Object.entries(scenarioExpectations)) {
  test(`mock scenario ${name} follows the event contract and reducer`, () => {
    const events = mockScenarios[name];
    assert.ok(Array.isArray(events) && events.length > 0);
    const calls = new Map();
    const results = new Set();
    for (const event of events) {
      assert.equal(typeof event.type, "string");
      assert.equal(typeof event.ts, "string");
      if (event.type === "status") {
        assert.ok(
          ["idle", "connecting", "live", "ending", "ended", "error"].includes(
            event.state,
          ),
        );
      } else if (event.type === "transcript") {
        assert.equal(typeof event.turn_id, "string");
        assert.ok(["user", "aria"].includes(event.role));
        assert.equal(typeof event.text, "string");
        assert.equal(typeof event.final, "boolean");
      } else if (event.type === "tool_call") {
        assert.equal(typeof event.call_id, "string");
        assert.equal(typeof event.name, "string");
        calls.set(event.call_id, event.name);
      } else if (event.type === "tool_result") {
        assert.equal(typeof event.call_id, "string");
        assert.equal(typeof event.name, "string");
        assert.ok(
          calls.has(event.call_id),
          `unpaired tool_result ${event.call_id}`,
        );
        assert.equal(calls.get(event.call_id), event.name);
        results.add(event.call_id);
      } else if (event.type === "summary") {
        assert.ok(event.summary && typeof event.summary === "object");
      } else if (event.type === "error") {
        assert.equal(typeof event.code, "string");
        assert.equal(typeof event.message, "string");
        assert.equal(typeof event.recoverable, "boolean");
      } else {
        assert.ok(
          ["interrupted"].includes(event.type),
          `unknown scenario event ${event.type}`,
        );
      }
    }
    for (const callId of calls.keys())
      assert.ok(results.has(callId), `tool_call ${callId} has no result`);
    const state = apply(events);
    assert.equal(selectVoiceState(state), expected.voice);
    assert.equal(state.turns.length, expected.turns);
    assert.equal(Boolean(state.summary), expected.summary);
    assert.equal(state.status.reason, expected.reason);
    if (expected.status) assert.equal(state.status.state, expected.status);
    if (expected.recoverable !== undefined) {
      assert.equal(state.error.recoverable, expected.recoverable);
      assert.equal(state.status.state, expected.status);
    }
  });
}
