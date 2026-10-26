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

## Temporary demo identity API (account-mode foundation)

Account mode uses a temporary demo identity, not real authentication. The
frontend creates one after the user enters a display name:

```http
POST /api/demo-sessions
Content-Type: application/json

{"name":"Priya"}
```

The backend returns `201 Created`, with `Cache-Control: no-store`:

```json
{"display_name":"Priya","credential":"<opaque-random-token>"}
```

Names are trimmed and must contain 1–80 visible characters. The credential is
high entropy, is returned only at creation, and is never logged or placed in a
URL. The backend stores only its SHA-256 digest. The browser should hold the
credential in tab-scoped `sessionStorage` across calls and screen/mode
navigation, clearing it on explicit reset; the browser removes it when the tab
closes. This bearer credential grants demo authorization; the entered name is
only a label and this is not secure real-world authentication.

Temporary identities live in process memory. An identity expires after 30
minutes without an authorized account-mode call; an authorized account-mode
`start_call` refreshes its inactivity timer. Expired records are pruned during
session creation or credential validation. A backend process restart clears
all identity state. This in-memory design is process-local and is not suitable
for multiple backend workers without sticky routing/shared state.

The HTTP endpoint configures CORS for `ALLOWED_HTTP_ORIGINS` (see
`backend/.env.example`) and does not enable credentialed cookies. CORS is a
browser policy, not authorization or rate limiting; non-browser clients can
still call the demo-identity creation endpoint. Browser code must not log the
returned credential.

Mock DB mode can opt into cross-call structured reference context without
creating an account or claiming fixture ownership:

```http
POST /api/mock-sessions
```

It returns `201 Created`, `Cache-Control: no-store`, and
`{"context_id":"<opaque-random-token>"}`. The token authorizes only temporary
conversation-reference state, not a personal identity. Store it in tab-scoped
`sessionStorage` separately from the account credential. It expires after the
same 30-minute inactivity interval or on backend restart. Legacy Mock DB calls
without a context ID remain supported, with context limited to one WebSocket.

## Client → Server

| Frame | Shape | Notes |
|---|---|---|
| JSON | `{"type":"start_call"}` | Backend opens the Gemini session. Sent once, after connect. Omitted `mode` retains the legacy Mock DB behavior. |
| JSON | `{"type":"start_call","mode":"mock_db"}` | Explicit existing Mock DB flow; fixture behavior remains unchanged. |
| JSON | `{"type":"start_call","mode":"mock_db","context_id":"<opaque-random-token>"}` | Optional mode-bound token enables structured context across Mock DB calls. It does not identify an account or change the sample fixture candidate set. |
| JSON | `{"type":"start_call","mode":"account","credential":"<opaque-random-token>"}` | Account mode requires a valid temporary identity credential. The backend validates it before connecting to Gemini. |
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
`call_summary` is template-generated and may contain multiple concise,
chronologically ordered highlights for successful major actions (such as order
placement, order viewing, and cancellation); failed or pending actions are not
described as completed. Summary construction is behind an interface and is
validated before sending.

### `error`

```json
{"type":"error","code":"BAD_MESSAGE","message":"...","recoverable":true,"ts":"..."}
```

Initial codes: `BAD_MESSAGE`, `SESSION_ACTIVE`, `GEMINI_UNAVAILABLE`,
`SESSION_LIMIT`, `ACCOUNT_SESSION_INVALID`, `MOCK_SESSION_INVALID`,
`ACCOUNT_FEATURES_NOT_READY`, and `INTERNAL`. If `recoverable` is false, the
backend closes the socket after sending the error. An account-mode call with a missing/invalid/expired
credential emits `ACCOUNT_SESSION_INVALID` and closes before creating a Gemini
session. Listing, lookup, reference resolution, and eligibility in account mode
operate only on the temporary identity's own orders; new identities start with
an empty list. Account cancellation uses action-bound confirmation and persists
only that identity's temporary order state. Unknown and non-owned IDs both
return `NOT_FOUND`; Mock DB fixtures are never candidates in account mode.
Account-mode `build_order_cart` uses the backend catalog and stores the resulting
temporary cart on the authorized identity; that cart is available on subsequent
calls for that identity and is isolated from other identities and Mock DB mode.
`list_order_carts()` returns only carts in the active authorized service, with a
placement status that distinguishes ready, placed, unavailable, and stale-price
quotes. This gives a later call a trusted way to discover its existing cart
without relying on provider memory or a customer-supplied internal ID.
Account-mode `place_order` uses the same action-bound confirmation contract as
Mock DB and creates only a simulated Processing order owned by that temporary
identity. Placement rechecks current prices/totals and COD eligibility; a
changed price fails closed and requires a new cart and confirmation. Repeated
placement for the same cart returns the original order idempotently. There is
no payment collection or fulfilment transaction. A provided but invalid or expired Mock DB
`context_id` emits `MOCK_SESSION_INVALID` and closes before Gemini connection;
omitting the token keeps legacy call-local behavior.

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
- Cancellation and placement use a one-time pending-action confirmation. The
  first mutation-tool call without `confirmation_id` returns
  `CONFIRMATION_REQUIRED` plus an ID bound to operation, exact target, current
  details, and finalized user turn; it does not mutate. Aria asks the customer
  to confirm and retries the same tool/target with that ID only if the next
  customer turn is a clear affirmative. Same-turn, stale (not the immediately
  next user turn), expired, mismatched, changed-detail, and replay attempts do
  not execute. Pending IDs expire after `PENDING_ACTION_TTL_SECONDS` (default
  300 seconds). Gemini interprets natural speech, so the backend cannot
  deterministically prove consent; ambiguous replies must fail closed and this
  residual model-interpretation risk is accepted for the demo. The backend
  remains authoritative for exact action, target, expiry, one-time use, and
  business-policy rechecks.
- Compression and session resumption are disabled in v1.
- Server limits are configurable: concurrent sessions, call duration, idle
  timeout, allowed WebSocket origins, HTTP CORS origins, and temporary demo
  identity inactivity timeout. Origin checks apply when Origin exists.
- Malformed JSON or an unknown control message returns `error BAD_MESSAGE`
  (recoverable); the session continues.
- Contract changes update this document first, then both sides.

## Runtime configuration

`GEMINI_API_KEY` is backend-only. `GEMINI_LIVE_MODEL` defaults to
`gemini-3.1-flash-live-preview`. Missing credentials fail `start_call` clearly; `/health`
does not require credentials. See `backend/.env.example` for abuse limits.

## Real Gemini audio smoke test

`backend/scripts/make_fixture.py` generates `backend/tests/fixtures/order_status_ord101.wav` using `espeak-ng`, then normalizes it to mono 16 kHz 16-bit PCM and prepends 300 ms of silence. WAV files are gitignored (`*.wav`) and are not committed. Regenerate the default fixture from `backend/` with `.venv/bin/python -m scripts.make_fixture`. The generator reports WAV format, duration, peak amplitude, and file size. The speech is synthetic; no customer recording is used. `ws_audio_smoke.py` also regenerates its selected fixture when it is missing (see `backend/scripts/ws_audio_smoke.py`, `run`, before WAV reading).

An alternate ID-first sentence can be generated with `.venv/bin/python -m scripts.make_fixture --order-id-first`, which writes `backend/tests/fixtures/order_check_ord101.wav`.

With the backend running and its real `GEMINI_API_KEY` configured in `backend/.env`, run from `backend/`:

```sh
.venv/bin/python -m scripts.ws_audio_smoke --url ws://127.0.0.1:8000/ws/call
```

Each smoke invocation opens one short real Gemini session and consumes API quota. It sends paced 20 ms PCM frames, gathers transcripts/tool events/audio, then gracefully ends the call. Optional arguments are documented by `--help`.
