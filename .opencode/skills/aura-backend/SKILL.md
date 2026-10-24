---
name: aura-backend
description: Apply Aura-wide backend conventions and coordinate FastAPI, Gemini Live, and business-tool work without duplicating their specialist instructions.
---

# Aura Backend

Use this as the project-wide backend entry point. Read `AGENTS.md` and relevant documents in `docs/` before implementing. Inspect existing code and Git status first.

## Responsibilities

- Keep backend work aligned with the actual requirements and contracts documented in `docs/`.
- Preserve the Python + FastAPI backend and one conversational LLM (Gemini Live) plus deterministic Python tools.
- Keep the Gemini session/SDK integration, HTTP/WebSocket transport, and business operations in separate modules with explicit interfaces.
- Treat backend data and deterministic validation as authoritative for prices, policies, eligibility, and order state.
- Keep secrets server-side and use environment configuration.
- Do not add a database, agent framework, extra LLM, queue, cache, or service without a concrete requirement.
- Do not duplicate domain facts or full implementation procedures that belong in `docs/` or specialist skills.

## Task workflow

1. Identify whether the task is primarily Gemini session work, FastAPI/transport work, or business-tool work; load the corresponding specialist skill when available.
2. Read relevant existing API contracts and requirements. If a contract is missing and a cross-layer decision is needed, propose a minimal contract before implementation.
3. Make the smallest coherent change; preserve existing user work and avoid unrelated refactors.
4. Test without external API usage where possible. Mock Gemini and external boundaries in unit tests.
5. Run relevant tests and report exact results, external API usage, and remaining limitations.

This skill is intentionally short: it coordinates project conventions rather than repeating the detailed rules in specialist skills.
