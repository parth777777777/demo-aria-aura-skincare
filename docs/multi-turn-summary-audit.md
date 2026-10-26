# Multi-turn Call Summary — Backend Audit

**Status:** The user approved implementation on branch
`multi-turn-summary-highlights`. Implementation is in progress. No Gemini calls
were made. Existing unrelated untracked frontend asset has not been touched.

## Scope and requirements

This audit covers generation of the post-call summary from backend transcript
and tool records, with focus on retaining multiple significant events in a
multi-turn conversation. Functional requirements call for structured post-call
summary fields `customer_intent`, `order_id`, `resolution_status`, and
`call_summary` (`docs/aura_skincare_functional_requirements.md:34-36, 81-82`).
The tool contract includes order lookup, placement, and cancellation, with
Python as source of truth for results and state (`docs/aura_tool_call_list.md:3-14, 30-35, 69-81`).
The fixture guidance requires subsequent lookups to reflect session mutations
(`docs/mock-orders.md:52-59`).

## Current capability and data flow

- Each WebSocket call owns `tools` and `transcript` collections
  (`backend/app/main.py:127-128`). Final input transcription and finalized
  assistant output are appended as turns (`main.py:231-261`); tool results are
  appended with name, order ID, and backend result (`main.py:339-344`).
- Graceful finish finalizes buffered assistant text, invokes the deterministic
  summary generator once, validates it, emits `summary`, then emits `ended`
  (`backend/app/main.py:154-170`).
- The current generator tracks a single intent and resolution by iterating tool
  records; later records overwrite earlier resolution (`backend/app/live/summary.py:26-52`).
  Its `call_summary` contains only a generic final-resolution sentence
  (`summary.py:65-67`).
- The summary contract has exactly four fields, and the WebSocket contract says
  the summary is backend-derived, `order_id` is from the most recent successful
  result, and summary text is template-generated
  (`backend/app/live/summary.py:14-23`; `docs/ws-event-contract.md:138-154`).
- Existing unit coverage checks validation and successful order-ID selection,
  but not multiple significant events
  (`backend/tests/test_live.py:402-413`).

## Limitations and risks

- An interaction such as successful placement, later order lookup, and
  successful cancellation is not represented as a sequence in `call_summary`;
  the current text reports only the final resolution.
- Tool records are append-ordered but do not have an explicit turn/timestamp
  field (`backend/app/main.py:339-341`). Therefore event ordering is tool
  execution order, not a proven total ordering against transcript turns.
- Some successful tools are informational or intermediate (for example
  eligibility checks and cart-building). Treating every successful tool call as
  a “major event” would make summaries noisy. A deterministic inclusion policy
  is needed.
- Result shapes differ between tools. Summary generation must only describe
  facts established by successful backend results, avoid asserting a state
  change from a staged/confirmation-required action, and stay within the
  existing 1000-character limit (`backend/app/live/summary.py:21-22`).
- Existing fields remain scalar. `customer_intent` and `resolution_status`
  cannot enumerate all topics/outcomes without changing the external contract;
  the most appropriate place for the event sequence is `call_summary`.

## Open design decisions

1. What precisely qualifies as a major event? Recommended initial scope:
   successful order placement, successful order-detail lookup, and successful
   cancellation; do not count eligibility checks, failed actions, or pending
   confirmation as completed events.
2. Should repeated lookups be deduplicated? Recommended: retain distinct major
   actions in execution order, but avoid repeating identical consecutive lookup
   highlights for the same order.
3. How should the legacy scalar fields be aggregated? Recommended: preserve
   their existing single-value schema and semantics, while making
   `call_summary` carry the ordered multi-event narrative. Exact intent and
   resolution precedence should remain unchanged in this slice unless test
   requirements necessitate a narrowly defined correction.
4. Should summaries include final order state? Recommended only when supported
   by the successful result payload; do not infer status from the tool name.

## Recommended implementation slice (requires approval)

Keep the four-field WebSocket schema unchanged. Extend deterministic summary
generation to construct concise, ordered highlights from successful backend
results for placement, order viewing, and cancellation, ensuring a place → view
→ cancel scenario includes all three and does not describe pending/failed
actions as completed. Add deterministic unit tests, including that sequence and
negative/pending cases. Update `docs/ws-event-contract.md` to clarify that
`call_summary` may contain multiple ordered highlights while preserving the
existing schema. Do not change transcript protocol, tool behavior, provider
integration, or call lifecycle. No real Gemini runs are needed or approved.

## Progress record

- **Audit:** Completed read-only. No backend code, tests, existing docs, or
  configuration changed. Only this new audit document was created.
- **Implementation/design:** Added ordered `call_summary` highlights for
  successful `place_order`, `get_order_details`, and completed `cancel_order`
  records. Failed/pending actions are omitted. Consecutive duplicate view
  highlights are deduplicated. The four-field schema and scalar field behavior
  remain unchanged.
- **Changed files:** `backend/app/live/summary.py`,
  `backend/tests/test_live.py`, `docs/ws-event-contract.md`, and this audit.
- **Tests/results:** Targeted summary tests → 3 passed, 1 warning. Full backend
  suite (`cd backend && .venv/bin/pytest -q`) → 154 passed, 2 warnings,
  3 subtests passed. `git diff --check` → clean.
- **Remaining risks:** Highlight ordering is tool execution order, as tool
  records do not carry transcript turn/timestamp metadata. Highlight text is
  bounded by the existing 1000-character schema validator; an unusually long
  sequence may fail validation rather than emit a partial summary. Existing
  intent and resolution remain scalar and retain their prior aggregation
  semantics. No provider behavior was exercised.
- **Provider runs:** approved 0; actual 0.
