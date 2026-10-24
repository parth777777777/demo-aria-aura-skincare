# WebSocket Event Contract (v1, draft)

Implementation contract, not a given requirement. The backend owns the Gemini
session and all business logic. The frontend only sends microphone audio and
call-control messages, and renders what the backend sends. The frontend never
computes policy, eligibility, prices, or tool results.

## Transport

- Endpoint: `ws://<backend>/ws/call` (one WebSocket = one call session).
- JSON text frames carry events/control. Binary frames carry audio.
- Every JSON message has a `type`. Receivers ignore unknown event types for
  forward compatibility; unknown client control messages receive `BAD_MESSAGE`
  as described below.
- The backend creates a fresh `OrderService` (session state) per connection and
  discards it on close.

## Client → Server

| Frame | Shape | Notes |
|---|---|---|
| JSON | `{"type":"start_call"}` | Backend opens the Gemini session. Sent once, after connect. |
| JSON | `{"type":"end_call"}` | Graceful end. Backend replies with `summary`, then closes. |
| Binary | Raw PCM16 mono audio | Microphone audio. **Provisional:** 16 kHz, 16-bit little-endian; verify against Gemini Live documentation. |

Browser microphone capture is usually 44.1/48 kHz float; the frontend must
resample/convert before sending. Chunk size is a tuning detail (about 20–100 ms
per frame).

## Server → Client

All JSON events include `ts` (ISO-8601 UTC, backend-generated).

### `status`

```json
{"type":"status","state":"idle|connecting|live|ending|ended|error","ts":"..."}
```

Drives the call status indicator and button states.

### `transcript`

```json
{"type":"transcript","turn_id":"t3","role":"user|aria","text":"...","final":false,"ts":"..."}
```

- Multiple events may arrive per `turn_id`: partial updates (`final:false`),
  then one `final:true`. The frontend replaces the text for a `turn_id`; it does
  not append blindly.
- `turn_id` order is chronological in the log.
- **Provisional:** assumes the SDK provides input/output transcription chunks.
  Verify availability and adjust partial/final semantics to actual SDK events.

### `tool_call`

```json
{"type":"tool_call","call_id":"c7","name":"get_order_details","args":{"order_id":"ORD-101"},"ts":"..."}
```

Display only (activity indicator). The frontend never responds to it.

### `tool_result`

```json
{"type":"tool_result","call_id":"c7","name":"get_order_details","result":{"ok":true},"ts":"..."}
```

`result` is the exact backend tool result: `{"ok":true,...}` or
`{"ok":false,"error":{"code":"...","message":"..."}}`. It matches the
`call_id` of its `tool_call`.

### `interrupted`

```json
{"type":"interrupted","ts":"..."}
```

The user barged in while Aria was speaking. The frontend immediately stops
playback and flushes its queued audio.

### `summary`

```json
{"type":"summary","summary":{"customer_intent":"...","order_id":null,"resolution_status":"...","call_summary":"..."},"ts":"..."}
```

Sent once after `end_call` (or when the backend ends the call). The functional
requirements specify these fields: `customer_intent`, `order_id`,
`resolution_status`, and `call_summary`. The backend builds and validates the
summary from its own transcript and tool-call record, never from client data.
The exact value vocabulary and whether `call_summary` is model-written remain
implementation decisions; do not treat client-supplied summary content as
authoritative.

### `error`

```json
{"type":"error","code":"BAD_MESSAGE","message":"...","recoverable":true,"ts":"..."}
```

Initial codes: `BAD_MESSAGE`, `SESSION_ACTIVE`, `GEMINI_UNAVAILABLE`,
`SESSION_LIMIT`, `INTERNAL`. If `recoverable` is false, the backend closes the
socket after sending the error.

### Audio (binary, server → client)

Raw PCM16 mono. **Provisional:** 24 kHz output, which differs from the input
rate; verify against Gemini Live documentation. The frontend plays chunks in
order and clears its queue on `interrupted`.

## Call lifecycle

1. Client connects and sends `start_call`.
2. Server sends `status: connecting`, opens the Gemini session, then sends
   `status: live`.
3. During streaming, client sends binary audio; server may send transcript,
   `tool_call`, `tool_result`, `interrupted`, and binary audio events.
4. Client sends `end_call` (or disconnects, or the server hits a limit).
5. For a graceful end, server sends `status: ending`, `summary`,
   `status: ended`, then closes.

## Rules

- Backend generates all IDs and timestamps.
- On disconnect without `end_call`, the backend cleans up the session and
  Gemini connection. No summary is guaranteed.
- A second `start_call` on the same socket returns `error SESSION_ACTIVE`.
- Malformed JSON or an unknown control message returns `error BAD_MESSAGE`
  (recoverable); the session continues.
- Contract changes update this document first, then both sides.

## Open items (resolve in the Gemini Live milestone)

- Exact audio formats and chunking (verify).
- Transcription availability and partial/final behavior (verify).
- Gemini session duration limits and how `SESSION_LIMIT` is triggered.
- Summary field value vocabulary and validation (required fields are listed
  above in accordance with the functional requirements).
- Whether the summary is deterministic from tool events and transcript, or
  includes a model-written text field.
