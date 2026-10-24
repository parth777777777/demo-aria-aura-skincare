---
name: gemini-live
description: Implement Gemini Live API integration in Aura, including SDK sessions, streaming audio events, interruptions, transcription, function calls, and safe tool responses.
---

# Gemini Live Integration

Use only for Gemini Live SDK/session/audio/tool-call work.

## Required workflow

- Read `AGENTS.md`, `aura-backend`, and the relevant `docs/` contracts first.
- Verify current official Gemini Live API documentation and the installed `google-genai` SDK before coding. Model support, event structures, audio modalities, and session methods can change.
- Avoid exploratory API calls. Use local mocks for unit tests; spend quota only on a deliberate end-to-end check that cannot be verified otherwise.

## Implementation rules

- Keep Gemini-specific SDK code behind a small, explicit service/session adapter.
- Keep API credentials on the backend and load them from environment configuration.
- Follow the current SDK's documented asynchronous session and event flow. Do not invent event names, payload fields, audio formats, or function-response APIs.
- Clearly separate incoming browser audio, Gemini session events, model tool requests, tool results, and outgoing browser events.
- Dispatch only declared, allowlisted tools. Validate tool name and arguments before calling application code.
- Return tool results to Gemini using the documented mechanism, then continue consuming the session as required by the SDK.
- Handle malformed tool calls, unknown functions, SDK exceptions, session expiry, browser disconnects, cancellation, and cleanup explicitly.
- Preserve event ordering where needed. Avoid unbounded queues or buffering that can make real-time audio lag.
- Do not log API keys or unnecessary raw audio/transcript content.
- Never let a tool result or model utterance falsely imply that an unconfirmed state-changing action succeeded.

## Tests and verification

- Unit-test the session adapter and event dispatcher with mocked SDK objects; tests must not require a real API key.
- Test unknown tools, invalid arguments, tool exceptions, disconnects, and cleanup.
- Run a real Gemini session only when necessary for a meaningful integration milestone; keep it short and report that API usage occurred.
- Report the exact SDK/model assumptions that remain unverified.
