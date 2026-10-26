# Stage 5 Conversation and Provider Quality — Read-only Audit

**Status:** Stage 5A approved and implemented: deterministic fake-provider
coverage for an unrelated turn after a placement quote, plus lifecycle cleanup
assertions for provider failure. Existing ambiguity and interruption tests were
reviewed and reused. No real Gemini calls were made. Stage 5B provider evaluation
remains unapproved and requires a separately defined run limit.

## Scope and worktree safety

Stage 5 is described in `docs/aria-capabilities-audit.md:134-138` as evaluating
conversation/provider quality, using deterministic fake-provider tests for
protocol behavior and requiring separate bounded approval for real model
behavior. This audit is limited to backend code/tests and backend-facing
contracts. At audit time, the worktree contains pre-existing frontend changes,
untracked frontend tests/components, `.agents/`, `.opencode/agents/backend.md`,
`opencode.json`, and root package/lock/skills files. None were modified. The
latest backend commit is `7563dec`; nothing was staged or committed by this
audit.

## Requirements and evaluation boundary

- Functional requirements ask for natural, concise, contextual conversation
  (`docs/aura_skincare_functional_requirements.md:26-34`) and include voice,
  order, policy, failure, transcript, and summary acceptance checks
  (`:122-135`). Hinglish and interruption are described as quality improvements
  (`:95-107`).
- The capability plan explicitly says fake tests do not establish model tool
  selection, reference resolution, affirmative confirmation, or naturalness;
  no real-provider run is approved by default
  (`docs/aria-capabilities-audit.md:59-61, 134-142`).
- Backend remains trusted for tool allowlisting, validation, order/policy state,
  and action confirmation; Gemini requests tools and interprets conversation
  (`.opencode/agents/backend.md:33-57`).
- User-visible order-card rendering is a separate frontend task and is not
  assessed or changed by this backend audit.

## Current capabilities and data flow (source evidence)

1. **Provider connection/configuration:** `GeminiLiveSession.connect` builds a
   Live config with the system prompt, sanitized callable declarations, audio
   transcription, and audio responses (`backend/app/live/session.py:42-63`).
   The event adapter repeatedly consumes provider interactions and emits
   events (`:77-98`). This adapter is where real SDK protocol behavior enters.
2. **Conversation instructions:** `ARIA_SYSTEM_PROMPT` directs order listing,
   safe reference resolution, policy use, confirmation, cart discovery, and
   account-vs-Mock wording (`backend/app/live/prompt.py:3-55`). Prompt text is
   instruction, not proof the model follows it.
3. **Trusted tool path:** WebSocket provider events parse input/output
   transcription and dispatch function calls (`backend/app/main.py:184-274`).
   `dispatch_tool` executes only through `execute_tool`; account calls recheck
   identity and serialize state access (`main.py:276-345`). Registry validation
   and backend results remain authoritative
   (`backend/app/tools/registry.py:61-146, 170-250`).
4. **Confirmation boundary:** backend binds pending action to action/target/
   details and user turn; the system prompt tells Gemini to retry only after a
   clear affirmative (`backend/app/tools/registry.py:208-250`,
   `backend/app/live/prompt.py:24-35`). Python does not classify speech
   semantically; the intended affirmative decision is made by the model.
5. **Summary path:** call finish constructs a deterministic summary from the
   backend transcript and tool records (`backend/app/main.py:154-170`). This is
   deterministic output behavior, not an assessment of model conversation
   quality.
6. **Existing fake coverage:** `backend/tests/test_live.py:35-60` defines a
   fake Live session; later tests exercise startup greeting, WebSocket lifecycle,
   transcript events, account flows, and scripted tool events. Registry tests
   validate schemas and deterministic backend outcomes. These tests can prove
   adapter/backend invariants under supplied event sequences, not that Gemini
   selects those events or interprets real speech correctly.

## Limitations and risks

- **No real provider evidence:** no current test establishes tool choice,
  transcription quality, conversational relevance, clarification behavior,
  language robustness, barge-in quality, or spoken-consent understanding.
- **Prompt compliance is probabilistic:** a fake provider can be scripted to
  follow the prompt, masking the principal Stage 5 risk. Never treat observed
  model confirmation as deterministic authorization; backend confirmation
  binding remains the safety boundary, with semantic consent residual risk
  documented at `docs/aura_tool_call_list.md:51-62`.
- **Evaluation reproducibility:** model/provider version, decoding behavior,
  audio input, expected outcomes, scoring rubric, run count, and acceptable
  failure thresholds need explicit definition. Small samples are observational
  only and do not support broad reliability claims.
- **Sensitive data:** use synthetic orders/names and synthetic or text-only
  scenarios. Do not log API keys, authorization headers, raw audio, or sensitive
  provider payloads. Any provider run consumes quota and requires user approval
  with a defined cap.
- **Scope creep:** do not change confirmation policy, schemas, externally
  visible WebSocket events, or business behavior under the label of evaluation
  without auditing and approving that implementation slice separately.
- **Frontend acceptance remains distinct:** transcript/tool-result rendering and
  the requested OrderCard display require frontend-owner work and cannot be
  verified by backend tests.

## Open decisions requiring user review

1. Which exact capability should Stage 5 first evaluate: deterministic fake
   event/lifecycle coverage, a bounded real-provider conversation smoke test,
   or both in separate slices?
2. If real Gemini evaluation is desired, what is the maximum number of runs,
   permitted input format (synthetic text/audio), model/configuration, and
   acceptance rubric? No real run is approved by this audit.
3. Should the first Stage 5 implementation slice add missing deterministic fake
   scenarios (for example ambiguous reference -> clarification/no mutation,
   unrelated turn during pending confirmation -> no placement, interrupted
   confirmation -> no placement, and provider failure cleanup), or first
   inventory existing tests and report gaps without changing them?
4. What failures are release-blocking versus merely recorded as model-quality
   observations? Backend authorization/policy invariants must remain release
   gates regardless of model scoring.

## Recommended staged path (approval required)

**Stage 5A — deterministic fake-provider coverage:** perform a test inventory,
then add only user-approved missing fake event scenarios. Assert backend
outcomes (no action on ambiguity/negative/unrelated input, safe cleanup on
disconnect/provider error/cancellation/timeout, correct tool-call ID response,
and scoped context) using scripted provider events. Do not claim those tests
prove real-model behavior. Avoid changing WebSocket event contracts unless
required; coordinate with frontend if any observable event changes.

**Stage 5B — bounded real-provider observation (optional, separate explicit
approval):** define synthetic scripted scenarios, exact model/configuration,
maximum run count and rubric first. Request no personal data and make no business
mutation outside the demo environment. Record exact runs and outcomes without
logging credentials/audio/provider payloads. Report findings as observations,
not authorization or general reliability proof. No code/API/quota action until
the user separately approves the specific run limit.

## Audit outcome

The backend capability plan has Stages 0A–4 marked complete; Stage 5A now adds
deterministic fake-session coverage. Actual Gemini conversational quality
remains unverified. Stage 5B requires a separate explicit provider-run approval.

## Stage 5A implementation progress

- **Approval/design:** User approved the recommended deterministic fake-provider
  slice: test unrelated-turn behavior after a placement quote and strengthen
  lifecycle cleanup assertions. No provider runs were approved; none were made.
- **Implementation:** Added a WebSocket test whose fake provider stages
  `place_order`, emits an unrelated customer turn, and ends without issuing the
  confirmation-bearing tool call. It asserts only `CONFIRMATION_REQUIRED` was
  returned and the identity has no orders. Strengthened the interrupted/provider
  failure test to assert the fake receive iterator is cancelled and the active
  session count returns to zero. Existing ambiguity test
  `test_ambiguous_reference_returns_candidates_without_guessing` and existing
  interruption/provider-error coverage were reviewed rather than duplicated.
- **Changed files:** `backend/tests/test_live.py`,
  `docs/stage5-conversation-quality-audit.md`.
- **Tests/results:** Targeted command:
  `cd backend && .venv/bin/pytest -q tests/test_live.py::test_unrelated_turn_after_placement_quote_does_not_place_order tests/test_live.py::test_interrupted_audio_provider_error_and_confirmation_guard tests/test_live.py::test_disconnect_cleans_up_live_session tests/test_order_resolution.py::test_ambiguous_reference_returns_candidates_without_guessing`
  → 4 passed, 1 warning. An initial targeted attempt found the provider-error
  fake did not mark its iterator cancelled; the fake's `finally` now records
  cancellation and the rerun passed. Full suite:
  `cd backend && .venv/bin/pytest -q` → 152 passed, 2 warnings,
  3 subtests passed. `git diff --check` → clean.
- **Remaining risks:** The unrelated-turn scenario scripts the fake provider not
  to retry; it verifies WebSocket/backend behavior under that event sequence,
  not Gemini's ability to recognize a topic change. Semantic consent remains
  probabilistic. No real provider calls.
- **Provider runs:** approved 0; actual 0.
