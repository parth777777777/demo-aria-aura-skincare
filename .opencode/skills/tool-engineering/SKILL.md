---
name: tool-engineering
description: Design safe, deterministic, model-callable tools for Aura, including argument validation, policy checks, order/product operations, confirmation, state transitions, and tests.
---

# Tool Engineering

Use for functions that Gemini can call and the deterministic Python services behind them. Read `AGENTS.md` and the relevant requirements, mock-data, and tool documents in `docs/` before changing domain behaviour.

## Design model-callable tools

- Expose only tools needed for the current user task. Keep the callable surface small and allowlisted.
- Give each tool a clear name, concise purpose, typed/required arguments, and a predictable result schema.
- Validate model-supplied arguments server-side: types, allowed values, lengths, identifiers, and required context.
- Treat model output as untrusted input. Never trust the model to provide authoritative prices, totals, order status, eligibility, or successful-action claims.
- Separate public model-callable tools from internal helper functions. Do not expose every Python function automatically.
- Return structured success/failure results that help the model explain outcomes without inventing facts.

## Deterministic domain logic

- Implement policies, eligibility, pricing, and state transitions in ordinary Python when they are expressible as explicit rules.
- Read and update the documented authoritative data source; avoid separate copies that can drift.
- Re-check order status, product availability, prices, and eligibility immediately before mutations.
- Require explicit user confirmation before state-changing actions. Confirmation must refer to the intended action and relevant arguments, not merely a generic earlier “yes”.
- Prevent duplicate mutations and order creation on retries where practical. Use explicit state transitions and idempotency controls appropriate to the mock implementation.
- Keep tool execution bounded and fail safely when resources are missing or state is invalid.
- Do not connect real payment, courier, or fulfilment services unless requirements explicitly change.

## Tests

- Unit-test successful cases, unknown identifiers, malformed arguments, ineligible actions, repeated calls, and invalid state transitions.
- Test boundary values from the domain requirements in `docs/`; don't hardcode domain policy values into this skill.
- Test that failed actions leave state unchanged and that a confirmed action changes only the intended record.
- Keep tests deterministic and free of external LLM/API calls.
- Report exact tests run and remaining gaps.
