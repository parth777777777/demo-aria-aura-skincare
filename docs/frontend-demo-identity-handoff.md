# Frontend Handoff: Temporary Demo Identity

This is the frontend implementation contract for the backend temporary-session
foundation. It does not authorize frontend code changes by the backend agent.
The backend API/WebSocket contract is defined in
[`ws-event-contract.md`](ws-event-contract.md).

## User-facing flow

1. Keep the current **Mock DB** entry path and its behavior. Existing calls may
   continue to send `{"type":"start_call"}`; the backend treats an omitted
   mode as `mock_db` for compatibility. Sending
   `{"type":"start_call","mode":"mock_db"}` is also supported.
2. Add a separate path to create a **demo identity**. Ask for a display name;
   do not ask for a password. This is temporary demo authorization, not a real
   account or authentication system.
3. After successful creation, retain the credential in tab-scoped
   `sessionStorage` so the same demo identity can be used across calls and page
   reloads in that tab. Do not clear it merely when navigating between screens
   or temporarily selecting Mock DB mode. Clear it when the user explicitly
   resets/leaves the demo identity; the browser clears `sessionStorage` when the
   tab closes.
4. When starting an account-mode voice call, include the credential in the
   `start_call` message exactly as shown below. Never put it in a URL, analytics,
   console output, error-report payload, or persistent `localStorage`.
5. For cross-call continuity in Mock DB mode, create an anonymous mock context
   using `POST /api/mock-sessions` and retain its separate `context_id` in tab
   `sessionStorage`. This token carries structured reference context only; it
   does not identify a customer or change the fixture data. Legacy Mock DB calls
   without it remain supported but retain context only for that WebSocket.

## Create the temporary identity

Request:

```http
POST /api/demo-sessions
Content-Type: application/json

{"name":"Priya Sharma"}
```

Success (`201 Created`; `Cache-Control: no-store`):

```json
{"display_name":"Priya Sharma","credential":"<opaque-random-token>"}
```

The backend trims the name and accepts 1–80 visible characters. Invalid names
or additional request fields return FastAPI validation status `422`. The
credential is a bearer secret: store it in `sessionStorage` and never log or
display it. The name is only a display label. CORS must include the deployed
frontend origin in backend `ALLOWED_HTTP_ORIGINS`; local development origins
are allowed by default. CORS is not authentication or protection from
non-browser clients.

Suggested storage keys:

```text
aura.demoIdentity.credential
aura.demoIdentity.displayName
```

These keys are suggestions, not backend requirements. Treat storage reads as
nullable and handle malformed/partial values safely. Creating a new identity
replaces the current tab's stored credential; the previous server-side record
becomes inaccessible from this tab and expires through backend cleanup.

## Start calls

Account-mode call:

```json
{"type":"start_call","mode":"account","credential":"<opaque-random-token>"}
```

Mock DB call (legacy-compatible):

```json
{"type":"start_call"}
```

or explicitly:

```json
{"type":"start_call","mode":"mock_db"}
```

Mock DB call with cross-call context:

```json
{"type":"start_call","mode":"mock_db","context_id":"<opaque-random-token>"}
```

The anonymous context is created with `POST /api/mock-sessions` and returns
`{"context_id":"<opaque-random-token>"}` with `Cache-Control: no-store`. Store
this under a distinct tab-scoped key (for example,
`aura.mockContext.contextId`); never reuse the account credential. A Mock DB
context is mode-bound, expires after 30 minutes idle or backend restart, and
contains only structured continuity such as the most recently resolved order
ID. The old no-token Mock DB start remains valid.

The backend validates an account credential before connecting to Gemini. Do
not start the microphone/Gemini experience as account mode if there is no
credential; route the user through identity creation first. Backend HTTP calls
must use the configured API base URL and WebSockets must use the existing
backend WebSocket URL; production deployments need the frontend origin in both
`ALLOWED_HTTP_ORIGINS` and `ALLOWED_WS_ORIGINS`.

## Expiry and errors

- Account identity state is in backend process memory. It is cleared on backend
  restart and expires after 30 minutes without an authorized account-mode
  `start_call` (the timeout is configurable). A tab may still have a credential
  after expiry or backend restart; handle the backend rejection by clearing the
  stale credential and returning to identity creation.
- Missing, invalid, or expired credential produces WebSocket `error` code
  `ACCOUNT_SESSION_INVALID` with `recoverable: false`; the backend closes the
  socket before Gemini is connected. Show a safe explanation and offer to
  create a new demo identity. Never echo the credential in the message.
- A missing/invalid/expired `context_id` when one is provided produces
  `MOCK_SESSION_INVALID`; clear the stale context ID and call
  `POST /api/mock-sessions` again. Do not send the account credential in Mock DB
  mode.
- Account-mode listing, lookup, reference resolution, eligibility, and confirmed
  cancellation are scoped to the temporary identity's own orders. New identities
  start empty; orders appear after account-mode placement is implemented. Guessed
  IDs from Mock DB or another account return the same `NOT_FOUND` as unknown IDs.
  `build_order_cart` is available in Stage 4A: it uses backend catalog prices and
  saves temporary carts to the authorized identity across calls. Other identities
  and Mock DB mode cannot access those carts. Account `place_order` now uses
  action-bound spoken confirmation and creates a simulated identity-owned order;
  it does not collect payment or initiate fulfilment. A changed catalog price
  fails closed and requires a newly built cart and fresh confirmation. Mock DB mode
  lists the three sample fixture orders, clearly labeled as demo data.
- Identity creation is currently public and has no rate limit. This is an
  assessment/demo feature, not a production authentication or abuse-control
  mechanism.

## Frontend implementation and acceptance checklist

- [ ] Landing page clearly preserves the Mock DB path and adds a demo-identity
      creation path without implying password-based login.
- [ ] Name input validates/normalizes UX consistently and handles HTTP `422`
      without losing the user's input.
- [ ] Successful creation stores the opaque credential only in tab
      `sessionStorage`; no logs, URLs, `localStorage`, analytics, or UI rendering
      expose it.
- [ ] Account-mode WebSocket starts send `mode: "account"` and the credential;
      Mock DB starts preserve the old behavior or send `mode: "mock_db"`. To
      enable cross-call Mock DB references, create/store a separate `context_id`
      and include it with `mode: "mock_db"`.
- [ ] Reloading the same tab preserves account-mode access; a fresh tab has no
      credential unless the browser explicitly duplicates tab session state.
- [ ] Invalid/expired-session errors clear stale credentials and provide a path
      to create a new identity. A backend restart is covered by this path.
- [ ] `ACCOUNT_FEATURES_NOT_READY` is presented as an unfinished capability,
      not as an order/action success.
- [ ] Tests verify Mock DB compatibility, account payload construction,
      sessionStorage use, error handling, and that credentials are not logged.
- [ ] The deployed frontend origin is configured in backend HTTP and WebSocket
      allowlists.

No frontend implementation or test was performed as part of this backend
handoff.

## Additional handoff: action confirmation flow

The backend has now added action-bound confirmation for the existing Mock DB
`cancel_order` and `place_order` tools. The same contract should be reflected
when account-mode mutations are added later. This is a voice flow; the frontend
does not make the authorization decision and should not add its own turn counter
or infer consent from transcript text.

### Backend tool-result behavior

- The first mutation tool call omits `confirmation_id`. It returns a
  `tool_result` with `ok: false`, `error.code: "CONFIRMATION_REQUIRED"`, and a
  `confirmation` object containing the one-time ID, action, exact target,
  current details, and `expires_in_seconds`. The action has **not** executed.
- Aria reads back the action and relevant target/details, then asks for spoken
  confirmation. If Gemini interprets the customer's immediately next finalized
  turn as a clear affirmative, it retries the same tool with the same target and
  `confirmation_id`.
- A successful backend `tool_result` is the only success signal. Same-turn,
  stale, expired, mismatched, changed-detail, and replay attempts return an
  error result and do not execute the action. Confirmation expires after the
  configured `PENDING_ACTION_TTL_SECONDS` (default 300 seconds).
- Natural-language consent interpretation is performed by Gemini and is
  probabilistic. The backend enforces session/action/target/detail/turn/expiry
  binding, but does not prove the transcript semantically means “yes.” The UI
  must not present model tool-call activity as an action or confirmation
  success.

### Frontend requirements for confirmation events

- Continue rendering `tool_call` and `tool_result` as activity/backend results;
  do not call tools from the browser or mutate frontend order/cart state based
  on Aria's words or a tool-call event.
- Do not display raw tool arguments. In particular, do not show or persist the
  internal `confirmation_id`; it is a one-time backend correlation value, not a
  user-facing confirmation control or session credential.
- Let the voice conversation carry the confirmation request and reply. The
  frontend should keep the normal microphone/audio flow active and must not
  treat unrelated transcript turns as consent.
- For `CONFIRMATION_REQUIRED`, show at most neutral pending/activity feedback;
  wait for a later successful `tool_result` before showing success. For any
  `CONFIRMATION_*` error or other failed result, do not claim the mutation
  happened; Aria's spoken follow-up is the primary explanation.
- A backend `tool_result` with `ok: true` remains authoritative for displaying
  a completed cancellation or placement. The frontend must not independently
  decide whether “yes,” “sure,” or another utterance is affirmative.

### Additional acceptance checks

- [ ] First `cancel_order` / `place_order` activity never appears as completed;
      only the successful backend result does.
- [ ] The UI does not render, log, or persist the one-time `confirmation_id`.
      It may passively receive it in backend `tool_call` activity, but never
      originates it in client control messages.
- [ ] Failed/stale/expired confirmation results never show action success.
- [ ] No frontend turn counter or transcript-based local authorization is added;
      natural confirmation remains in the voice/backend tool flow.
- [ ] Account-mode cancellation and simulated placement use backend tool results;
      the frontend must not infer authorization or confirmation success locally.
