# Frontend call-feature integration guide

This guide connects the Aura call experience to the backend contract. It is for
frontend implementation; the backend remains the authority for Gemini, order
facts, policies, tools, and call summaries.

## Product direction

The intended experience is simple and conversational: the customer starts a
call, Aria greets them, they talk naturally for as long as the session permits,
and the customer can end the call with a clear control. Avoid imposing a
frontend turn counter or forcing a scripted sequence. Reflect actual connection,
listening, thinking, and speaking events rather than simulating them.

There are two current backend limitations to keep visible during implementation:

- The WebSocket `start_call` currently connects Gemini and reports `live`; it
  does not itself trigger an opening greeting. The desired greeting needs a
  backend-owned startup behavior. Do not fake it with a synthetic customer
  utterance or browser-side Gemini call.
- The conversation has no frontend turn limit, but the backend currently has
  configurable idle and maximum-duration limits (defaults: 120 and 600 seconds).
  “No limit” means no arbitrary frontend turn cap, not an unlimited provider or
  server session. See `backend/.env.example`.

The End Call button is the customer-controlled end path. It sends `end_call`;
the backend finalizes its summary and closes. A future goodbye-triggered end
tool is not part of this contract. If added later, it must be designed and
implemented on the backend first; the frontend should not infer that ordinary
goodbye language means the call is over.

## Ownership boundaries

- The browser connects only to FastAPI at `/ws/call`; Gemini credentials and
  direct Gemini API calls stay backend-only.
- The backend owns the Live session, tool dispatch, order/session state, policy
  decisions, prices, confirmation checks, and summary.
- The frontend owns permission UX, microphone/audio resources, WebSocket
  transport, playback, call controls, transcript presentation, and honest
  display of backend state/results.
- Treat tool events as display/activity information. Never execute tools,
  calculate eligibility/pricing, or claim an action succeeded based on model
  wording; use the backend result.

## Transport and lifecycle

See [`ws-event-contract.md`](ws-event-contract.md) for the complete versioned
event contract. The essential flow is:

1. Only after an explicit user action, request microphone permission and open
   one WebSocket to `ws://<backend>/ws/call` (or `wss://` in production).
2. After the socket opens, send `{"type":"start_call"}` once. Render connecting
   until the backend reports `status: live`.
3. Capture mono PCM16 little-endian microphone frames at 16 kHz and send them as
   binary WebSocket messages. Browser capture is commonly float at 44.1/48 kHz,
   so conversion/resampling is required. Do not log or retain raw audio.
4. Play backend binary audio chunks in arrival order. Output is mono PCM16 at
   24 kHz. On `interrupted`, stop active playback and flush queued chunks.
5. On the customer pressing End Call, stop microphone capture immediately and
   send `{"type":"end_call"}` if the socket is open. Keep consuming events until
   `status: ended` or socket close; show the summary if received.
6. On disconnect/error, stop tracks, close/disconnect audio nodes, stop playback,
   detach listeners, and release the socket. Prevent duplicate starts and make
   cleanup safe to call more than once.

The graceful backend end order is `status: ending`, optional final transcript,
`summary`, `status: ended`, then socket close. A disconnect without `end_call`
still cleans backend resources but does not guarantee a summary.

## Events the UI should reflect

- `status`: drive controls and call indicator from `idle`, `connecting`, `live`,
  `ending`, `ended`, or `error`; display the supplied end reason when useful.
- `transcript`: upsert by `turn_id`, preserving role, chronological order, and
  `final`; partial updates replace that turn rather than append duplicates.
- `tool_call` / `tool_result`: pair by `call_id`; show activity only. The backend
  result is authoritative.
- `interrupted`: stop/flush Aria playback promptly.
- binary server frames: enqueue in order for playback; never treat them as JSON.
- `summary`: display the backend-provided summary fields without inventing
  missing facts.
- `error`: display the safe backend message and respect `recoverable`. Unknown
  event types should be ignored for forward compatibility.

The backend may emit `provider_activity` as an informational event; it is not a
user turn and must not be used to fabricate a transcript or success state.

## Natural-conversation UX requirements

- Keep the main interaction voice-first and let the user speak without a fixed
  turn quota. Show live transcript updates without forcing the user to wait for
  an artificial “next question” step.
- Make Listening/Thinking/Speaking indicators follow socket, transcript,
  provider activity, and playback state. Do not claim Aria is speaking before
  audio arrives or that an action succeeded before its tool result.
- Keep End Call visible and usable during connecting, listening, and playback;
  handle a hang-up while startup is still in progress.
- Explain microphone denial, connection failure, provider error, disconnect,
  and session-limit endings clearly and accessibly. Never surface secrets or
  binary payloads in UI/logging.
- Preserve keyboard access, visible focus, responsive layout, and reduced-motion
  preferences. Motion should reinforce actual call state, not substitute for it.

## Source of truth and verification

- WebSocket frames, audio formats, event payloads, and lifecycle:
  [`ws-event-contract.md`](ws-event-contract.md).
- User-facing call and product requirements:
  [`aura_skincare_functional_requirements.md`](aura_skincare_functional_requirements.md).
- Tool names and backend authority:
  [`aura_tool_call_list.md`](aura_tool_call_list.md) and the backend registry.

If implementation needs a new message, event, greeting trigger, end-call
behavior, or audio format, propose a coordinated contract change rather than
inventing a frontend-only protocol. Verify frontend changes with the available
tests, `npm run lint`, `npm run format:check`, and `npm run build` from
`frontend/`; do not spend Gemini quota for UI-only verification.
