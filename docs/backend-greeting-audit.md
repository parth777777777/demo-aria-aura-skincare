# Backend greeting audit (read-only source audit)

## Scope and evidence

This file began as a read-only audit and now records the approved greeting implementation. The implementation changes only backend code/tests and this document. No Gemini API request was made.

## Current behavior and startup path

1. `/ws/call` validates an optional origin, accepts the socket, allocates per-connection state (including `transcript`, `confirmation`, and `user_turn`), and reserves a concurrency slot: `backend/app/main.py:52-86, 215-224`.
2. Client `start_call` checks the backend key, emits `connecting`, constructs the configured live adapter and awaits `connect()`: `backend/app/main.py:300-319`.
3. After successful connection it records the start time, clears the provider-closed signal, emits `live`, then creates the provider event task: `backend/app/main.py:319-326`. No greeting is sent in this path.
4. The main task receives browser frames. Binary frames received after `live` are forwarded to `live.send_audio`: `backend/app/main.py:256-291`. There is no explicit startup barrier preventing audio from racing a hypothetical greeting send.
5. Provider events are consumed asynchronously: `backend/app/main.py:111-123`. Final input transcription increments `user_turn` and appends a `user` transcript row; interim input is emitted but not appended: `backend/app/main.py:156-166`. Output transcription accumulates in `output_text`, emits partial Aria transcript, and is appended at interruption or turn completion: `backend/app/main.py:167-190`.
6. Tools receive the current `user_turn` as `finalized_user_turn`; confirmation state is per WebSocket: `backend/app/main.py:203-214`. Thus an injected greeting sent with explicit user role can, depending on provider events, be transcribed as user input and increment the counter used by confirmation logic. That SDK/model event behavior is not established by source tests.
7. Graceful end emits ending, finalizes any buffered Aria text, generates summary from backend transcript/tool history, emits ended, and closes: `backend/app/main.py:91-109`. Disconnect and all paths close the live adapter, cancel/await the event task, and release the concurrency slot: `backend/app/main.py:331-379`.

## `send_text` and intro smoke evidence

`GeminiLiveSession.send_text(text)` calls `session.send_client_content(turns={"role":"user","parts":[{"text":text}]}, turn_complete=True)`: `backend/app/live/session.py:68-71`. This is explicitly a user-role turn in the wrapper implementation; it is not a backend/system-role greeting API. The unit test asserts exactly this payload: `backend/tests/test_live.py:59-74`.

The intro smoke defines a test-only trigger, explicitly labels it “not a customer turn,” then calls the same `send_text` path as the subsequent customer prompts: `backend/scripts/intro_convo_smoke.py:26-33, 98-105, 138-148`. It checks for nonempty output transcription, audio bytes, and no tool call; it does not exercise the WebSocket handler, its transcript bookkeeping, user turn counter, confirmation guard, concurrent microphone arrival, interruption, or teardown on startup-send failure. It is a real-Gemini script and each run uses one short session/quota (`backend/scripts/intro_convo_smoke.py:1-4, 193-199`). Its source and tests do not prove provider behavior; this audit did not run it.

## Risks and facts versus unverified behavior

- **Verified from source:** no startup greeting currently occurs; `live` is emitted before provider task creation; the normal user `send_text` payload has role `user`; final input transcription increments `user_turn`; final user text is stored in transcript; tool confirmation uses this counter; interruption finalizes buffered output and emits `interrupted`; `end_call` and disconnect have cleanup paths.
- **Risk if naively added:** calling `send_text` with greeting text can represent it to Gemini as a user turn. If provider input transcription reports it, it could be shown/stored as customer speech and advance confirmation state. Whether that happens is SDK/model-dependent and unverified here.
- **Ordering/race:** because browser binary frames can be handled as soon as the receive loop resumes and events run concurrently, startup greeting send versus first microphone audio needs an explicit ordering decision. Source alone cannot establish the provider's ordering semantics.
- **Interruption/end:** automatic greeting audio should use the existing provider event path so audio, transcript, `turn_complete`, and interruption handling remain unified. A hang-up during connect or greeting must not leave a send running after `finish`/close; currently `finish` does not itself close the provider session, while final cleanup does. Lifecycle interaction should be tested with fakes.
- **Startup failure:** `connect()` exceptions are caught and yield `GEMINI_UNAVAILABLE`, error finish, and final cleanup. A greeting-send exception would need to receive equivalent handling and must not leave the active-session slot/task behind.
- **SDK/model unknowns:** whether an alternative non-user role/content mechanism exists and is accepted by the configured SDK/model; whether sending `send_client_content` triggers the expected response/audio/transcription; whether provider input transcription echoes supplied client text; and precise ordering relative to realtime audio are unverified. No SDK/model behavior is claimed as tested.

## Implemented design and remaining provider uncertainty

On successful `start_call`, backend connects, sets the startup gate, emits `live`, creates the provider event task, and launches one greeting task. The consumer signals readiness before it begins iterating `live.events()`; only then does the task call `live.send_text("The customer just connected. Greet them and introduce yourself briefly.")`. Its output audio/transcription remains handled by the existing provider event loop. Browser audio is held in a bounded 100-frame FIFO deque while the greeting turn is pending. It is not sent to Gemini on an interruption event; the opening greeting is intentionally non-interruptible by speech in this MVP. On `turn_complete`, the backend flushes retained frames in order before forwarding newly received audio. The deque's `maxlen=100` behavior discards the oldest frame when full. End Call remains readable during the gate; it cancels/cleans up normally without flushing queued audio. No new event/protocol or frontend work is introduced. Input transcription is suppressed until actual browser audio begins forwarding, so an echo of the user-role cue cannot create customer transcript rows or increment `user_turn`. Startup-send errors use the safe Gemini-unavailable error and normal finish/cleanup; teardown cancels the outstanding greeting task.

The pinned SDK source for `send_client_content` says client content is added to context in order, says `turn_complete=True` causes a response, and warns that interleaving `send_client_content` and `send_realtime_input` is not recommended (`backend/.venv/lib/python3.14/site-packages/google/genai/live.py:170-218`). It does not prove model output, transcript echo behavior, event ordering, interruption timing, or that a greeting reliably completes before audio is released. The gate avoids intentional overlap in the backend's send calls, but at most 100 frames are retained and excess frames overwrite oldest deque entries; this is a deliberate bounded-memory tradeoff and may lose initial speech. The adapter's source confirms `send_text` uses role `user` (`backend/app/live/session.py:68-71`); attribution safety is enforced by backend event bookkeeping, not guaranteed by Gemini. A real provider run is needed to check that generated greeting output occurs and that provider events fit the assumed sequence. No such run was made.

## Deterministic tests and evidence

`backend/tests/test_live.py::test_ws_startup_greeting_is_once_after_consumer_ready_and_uses_normal_events` verifies cue count, consumer readiness, normal Aria transcript/audio flow, and synthetic input suppression. `backend/tests/test_live.py::test_ws_startup_greeting_failures_and_end_during_send_clean_up` verifies no cue on connection failure, cleanup on send failure, and End Call during a blocked cue send. `backend/tests/test_live.py::test_ws_startup_audio_is_held_fifo_and_oldest_frame_dropped` verifies no early audio forwarding, FIFO flush after turn completion, and dropping the oldest of 101 queued frames. Existing fake interruption and disconnect tests remain part of the full suite. These are deterministic application tests only; they do not establish actual provider/model behavior.

### Buffered forwarding review fix

Both FIFO-drained and newly received audio now call the same `forward_audio` routine. WebSocket binary receive counters are incremented exactly once on receipt, including frames queued during the greeting. Successful provider sends update success/timing/forwarded-byte counters identically, and the existing every-50-success `audio_forwarded` acknowledgment applies to buffered sends too. A buffered-send exception emits the same non-recoverable `GEMINI_INPUT_FAILED`, finishes the call, and follows normal provider/task cleanup instead of escaping to generic `INTERNAL` handling. Deterministic tests: `test_buffered_audio_uses_shared_counters_and_acknowledgment` and `test_buffered_audio_send_failure_uses_normal_gemini_input_error`.

## Assumed or skipped

- No credentials or `.env` content was inspected or printed.
- All greeting tests use fake Live sessions. No real Gemini call was made.
- The provider's generated greeting, any user-role cue echo behavior, and actual event/completion timing remain unverified.

## Later-stage workflow log

Record each subsequent greeting stage here after audit review; do not treat this audit as implementation approval.

| Stage/date | Changes / commit | Test commands and raw results | Explicitly approved real-Gemini runs (count/limit) | Notes |
|---|---|---|---|---|
| Stage 1 — read-only audit | Created `docs/backend-greeting-audit.md`; no commit | Source inspection only | 0; none approved or run | |
| Stage 2 — design review | `send_text` path approved by user | No tests | 0; none approved or run | User selected user-role cue despite documented provider uncertainty |
| Stage 3 — implementation | `backend/app/main.py`, `backend/tests/test_live.py`, this document; no commit | `cd backend && .venv/bin/pytest -q tests/test_live.py -k 'startup_greeting or startup_greeting_failures'` — 2 passed, 17 deselected | 0; none approved or run | |
| Stage 4 — docs and verification | Clarified MVP behavior and shared buffered/live audio-forwarding path; no commit | Focused: `cd backend && .venv/bin/pytest -q tests/test_live.py -k 'buffered_audio or startup_audio'` — 3 passed, 19 deselected. Full: `cd backend && .venv/bin/pytest -q` — 115 passed, 2 warnings, 3 subtests passed. `git diff --check` — exit 0, no output | 0; none approved or run | Warnings: Starlette/httpx deprecation and google-genai/Python deprecation |
