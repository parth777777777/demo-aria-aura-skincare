---
name: fastapi-backend
description: Design and implement Aura's FastAPI HTTP and WebSocket endpoints, Pydantic schemas, configuration, async lifecycle, errors, and backend tests.
---

# FastAPI Backend

Use for HTTP API, WebSocket transport, app lifecycle, schemas, configuration, and general Python service structure. Read `AGENTS.md`, relevant `docs/`, and existing code first.

## Structure and interfaces

- Keep endpoint handlers focused on transport concerns. Put domain operations in service/tool modules and request/response shapes in Pydantic schemas where useful.
- Keep the WebSocket transport contract explicit and consistent with the frontend. If `docs/api-contracts.md` exists, follow it; otherwise inspect existing implementation and propose a minimal shared contract before changing both ends.
- Keep Gemini SDK/session mechanics in the Gemini integration module, not spread through route handlers.
- Keep order/policy logic in domain services, not inside HTTP or WebSocket handlers.
- Use async functions for actual asynchronous I/O; avoid blocking the event loop with synchronous long-running operations.
- Validate incoming HTTP payloads and WebSocket messages. Enforce sensible size/type limits and handle malformed messages safely.
- Use consistent error response shapes and appropriate HTTP status codes.
- Configure CORS for known development/deployment origins. Do not use wildcard origins with credentials.
- Manage startup/shutdown, session cancellation, WebSocket disconnects, and resource cleanup deliberately.
- Load settings from environment variables; never hardcode secrets.

## Dependencies and maintainability

- Prefer FastAPI, Pydantic, Uvicorn, and the existing project dependencies.
- Add a dependency only when it materially simplifies a real requirement.
- Avoid premature repository/service abstractions and excessive generic base classes.
- Keep modules small with clear responsibilities, but don't create empty files solely to match a planned tree.

## Tests

- Test HTTP routes with FastAPI's supported test client and test WebSocket behaviour where practical.
- Test validation failures, unknown resources, server errors, and disconnect handling.
- Keep tests independent of Gemini credentials and network access unless an explicit integration test requires them.
- Run relevant tests and report exact commands/results. Never claim unrun checks passed.
