# WebSocket Event Contract (v1)

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
| JSON | `{"type":"end_call"}` | Graceful end: status ending, summary, status ended, then close. |
| Binary | Raw PCM16 mono audio | 16-bit little-endian, 16 kHz. Gemini MIME label: `audio/pcm;rate=16000`. |

Browser microphone capture is usually 44.1/48 kHz float; the frontend must
resample/convert before sending. Chunk size is a tuning detail (about 20–100 ms
per frame).

## Server → Client

All JSON events include `ts` (ISO-8601 UTC, backend-generated).

### `status`

```json
{"type":"status","state":"idle|connecting|live|ending|ended|error","reason":"user_ended|session_limit|error","ts":"..."}
```

Drives the call status indicator and button states.

### `transcript`

```json
{"type":"transcript","turn_id":"t3","role":"user|aria","text":"...","final":false,"ts":"..."}
```

- For both roles, multiple events may arrive per `turn_id`; frontend replaces
  the displayed text by `turn_id`. User speech uses Gemini interim and finalized
  input transcription. Aria output chunks are accumulated by the backend, which
  emits the complete text so far with `final:false`, then `final:true` at turn
  completion or interruption.
- `turn_id` order is chronological in the log.

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
V1 values are deterministic: `customer_intent` is one of `order_status`,
`cancellation`, `return`, `damaged_product`, `delivery_info`, `place_order`,
`policy_question`, `out_of_scope`, `unclear`; `resolution_status` is one of
`resolved`, `not_eligible`, `unresolved`, `out_of_scope`, `no_interaction`.
`order_id` is the order from the most recent successful tool result or null.
`call_summary` is template-generated. Summary construction is behind an
interface and is validated before sending.

### `error`

```json
{"type":"error","code":"BAD_MESSAGE","message":"...","recoverable":true,"ts":"..."}
```

Initial codes: `BAD_MESSAGE`, `SESSION_ACTIVE`, `GEMINI_UNAVAILABLE`,
`SESSION_LIMIT`, `INTERNAL`. If `recoverable` is false, the backend closes the
socket after sending the error.

### Audio (binary, server → client)

Raw PCM16 mono, 24 kHz output. The frontend plays chunks in
order and clears its queue on `interrupted`.

## Call lifecycle

1. Client connects and sends `start_call`.
2. Server sends `status: connecting`, opens the Gemini session, then sends
   `status: live`.
3. During streaming, client sends binary audio; server may send transcript,
   `tool_call`, `tool_result`, `interrupted`, and binary audio events.
4. Client sends `end_call` (or disconnects, or the server hits a limit).
5. For a graceful end (client end, go_away, connection expiry, or duration/idle
   cap), server sends `status: ending` with `reason`, `summary`, `status: ended`
   with the same `reason`, then closes.

## Rules

- Backend generates all IDs and timestamps.
- On disconnect without `end_call`, the backend cleans up the session and
  Gemini connection. No summary is guaranteed.
- A second `start_call` on the same socket returns `error SESSION_ACTIVE`.
- Synchronous function calls only. Tool responses preserve provider call `id`
  and function `name`; cancelled pending call IDs receive no response.
- Cancellation and placement require a confirmation guard: first call returns
  `CONFIRMATION_REQUIRED`; only a retry for the same target after a later
  finalized user turn can execute. This prevents same-turn model actions but
  does **not** prove what the user said. The source requirements provide no
  exact confirmation sentence; Aria must explicitly ask for confirmation.
- Compression and session resumption are disabled in v1.
- Server limits are configurable: concurrent sessions, call duration, idle
  timeout, and allowed WebSocket origins. Origin checks apply when Origin exists.
- Malformed JSON or an unknown control message returns `error BAD_MESSAGE`
  (recoverable); the session continues.
- Contract changes update this document first, then both sides.

## Runtime configuration

`GEMINI_API_KEY` is backend-only. `GEMINI_LIVE_MODEL` defaults to
`gemini-3.8-live`. Missing credentials fail `start_call` clearly; `/health`
does not require credentials. See `backend/.env.example` for abuse limits.
