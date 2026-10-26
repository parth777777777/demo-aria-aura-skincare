# Stage 4 Account Commerce — Read-only Audit

**Status:** Stage 4A complete. Stage 4B approved: account-only simulated order
placement from identity-owned persistent carts, with action-bound confirmation,
current-price/policy revalidation, identity-owned order persistence, idempotent
retry, and in-process same-identity serialization. If catalog price changes,
placement fails closed and requires a newly built cart and fresh confirmation.
No real Gemini calls were made.

## Scope and worktree safety

Stage 4 in `docs/aria-capabilities-audit.md:126-130` calls for account-mode
catalog/inventory access, account-owned carts, and simulated order placement,
with unlimited stock, backend prices, confirmation, and idempotency. This audit
uses the current worktree as inspected on 2026-10-26. Existing modifications in
backend files and documentation are present, as are extensive frontend changes
and protected/untracked root entries; none were edited by this audit. In
particular, Stage 3 backend edits are already in progress in the worktree and
must be preserved. Nothing was staged or committed.

## Requirements and contracts

- Functional requirements define source-owned prices and shipping/COD policy
  (`docs/aura_skincare_functional_requirements.md:40-53`), while payment
  collection and real order-system integration are explicitly excluded
  (`:137-149`).
- Tool list names `build_order_cart` and `place_order` and points to the
  implementation contract (`docs/aura_tool_call_list.md:46-62`).
- Current cart contract defines catalog-based cart building, totals, COD limit,
  confirmation, and repeat-placement idempotency, but scopes carts/orders to
  one in-memory `OrderService` per call/session
  (`docs/cart-order-tool-contract.md:7-27, 38-39`).
- The approved Stage 4 direction says each temporary identity uses the same
  catalog and unlimited stock; identity cart/order state is isolated, temporary,
  and placement rechecks prices (`docs/aria-capabilities-audit.md:85,
  126-130`). This is a demo identity/bearer credential, not authentication.

## Current capabilities and data flow (source evidence)

1. `DemoSessionStore` creates account sessions with `orders: []` and structured
   context (`backend/app/domain/demo_sessions.py:48-73`). It stores session
   state process-locally under a lock and returns deep copies on authorization
   (`:75-89`). Current persisted fields do not include a cart or placement
   idempotency state. `replace_account_orders` replaces only the order list
   (`:98-113`).
2. At account `start_call`, the WebSocket authorizes the credential and creates
   an `OrderService` from the identity's owned orders with fixture fallback
   disabled (`backend/app/main.py:472-506`; constructor
   `backend/app/domain/orders.py:19-32`). Thus the service—and its carts—are
   recreated for each call.
3. The account tool dispatcher revalidates the credential for every tool call,
   checks identity consistency, then currently explicitly returns
   `ACCOUNT_FEATURES_NOT_READY` for `build_order_cart` and `place_order`
   (`backend/app/main.py:276-324`). After other tools it persists the service's
   owned orders (`:323-329`). Account mode does not fall through to the fixture
   service.
4. The allowlisted registry already declares both tools and validates cart
   fields, quantities, distinct products, and payment method
   (`backend/app/tools/registry.py:26-30, 51-55, 79-102`). It routes validated
   cart construction and placement to `OrderService` (`:168-203`).
5. `OrderService.build_order_cart` matches product IDs/names against the
   canonical catalog, gets prices from `get_products()`, computes subtotal,
   shipping, and COD eligibility, and stores a generated cart in its local map
   (`backend/app/domain/orders.py:162-193`). `place_order` checks that local
   cart, rechecks COD, creates a Processing order, and keeps a local
   cart-to-order idempotency mapping (`:195-214`). These operations are
   deterministic but currently per-service, not identity-persistent.
6. Catalog access reads the cached `products.json` and validates only ID, name,
   and integer price (`backend/app/data/products.py:16-40`). There is no stock,
   availability, variant, or inventory state. The agreed MVP is unlimited
   stock, so catalog membership can represent demo availability, but must not
   be described as a real stock count or reservation.
7. Confirmation state is local to one WebSocket call
   (`backend/app/main.py:127-130`) and the registry binds `place_order` to the
   cart detail snapshot and a fresh turn (`backend/app/tools/registry.py:224-275`).
   This supports confirming within the same call, provided the cart survives
   for that call. The current service has no price-version/snapshot mechanism;
   current static catalog prices are recalculated when a cart is built, and
   placement only checks COD from the stored cart (`orders.py:172-214`).

## Findings, limitations, and risks

- **Primary gap:** Cart construction and placement are gated for account mode;
  although domain tools exist for Mock DB, account dispatch does not expose them.
- **Cross-call cart lifetime is undecided by current contract:** existing cart
  storage belongs to one call-scoped service. The Stage 4 wording can mean
  account identity-scoped carts across calls, while the cart contract says
  per-call. The implementation should not silently select one. Same-call-only
  carts are a smaller slice; cross-call carts require durable-within-process
  session fields and lifecycle decisions.
- **Atomicity/concurrency:** identity orders are copied into a service, then
  replaced after a tool call. Concurrent WebSockets for one identity can
  overwrite one another; same-identity cart/order operations are not one atomic
  transaction. The store lock does not cover a full read-modify-write service
  operation. No database or multi-worker coordination exists.
- **Order IDs:** each fresh `OrderService` starts its generated sequence at 201
  (`orders.py:31`), so independently created services can collide. Account
  placement must allocate unique IDs within the account state, including
  concurrent calls; identifiers need only be demo-safe, not globally durable.
- **Price/confirmation:** The tool contract binds confirmation to cart details,
  but a cart currently stores its built price. If catalog prices can change
  during the cart lifetime, placement needs a declared policy: reprice and
  invalidate/reconfirm on change, or explicitly freeze the displayed price for
  the temporary cart. Current catalog is static, but this assumption should be
  explicit and tests should verify the chosen behavior.
- **Payment semantics:** `PREPAID` is only a label; no payment is collected.
  Avoid implying payment completion or transmitting payment credentials.
- **Inventory semantics:** unlimited stock requires no decrement/reservation;
  a new “inventory” endpoint/tool is not necessary absent a user-facing need.
  Product availability should remain deterministic and backend-owned.
- **Session lifecycle:** process restart clears identities, consistent with the
  temporary demo contract. Credential expiry is refreshed on authorized
  account calls. Cart/context retention must follow the same identity expiry
  and never enter Mock DB mode or another identity.
- **Confirmation residual risk:** backend checks binding/freshness/expiry, but
  Gemini interprets spoken consent; that interpretation is not proof of consent
  (`docs/aura_tool_call_list.md:48-59`). Do not represent this demo flow as
  production authorization.
- **Testing/provider boundary:** current deterministic tests cover the general
  cart/order service and tool confirmation, but do not establish model tool
  selection or spoken consent accuracy. No real provider call is justified or
  approved for this stage.
- **Frontend coordination:** the frontend is already modified in the worktree,
  but this backend audit does not inspect or change its implementation. Any
  externally observable account commerce error/result or new inventory tool
  requires the frontend owner to coordinate contract consumption. Existing
  frontend-facing handoff is `docs/frontend-demo-identity-handoff.md`.

## Open decisions requiring review

1. **Resolved:** carts persist across calls within the same demo identity.
2. **Resolved:** user approved Stage 4B with price recheck at placement and
   fail-closed behavior requiring a newly built cart and fresh confirmation if
   price changed.
3. **Resolved:** user approved in-process serialization of same-identity
   mutations to avoid duplicate IDs or lost updates.
4. **Resolved:** no separate product/inventory API was added; the catalog is
   exposed in the cart tool declaration. `list_order_carts()` was added so
   account carts from prior calls can be rediscovered without provider memory or
   customer knowledge of an internal ID.
5. What exact account result/error contract should replace
   `ACCOUNT_FEATURES_NOT_READY`, and what neutral behavior should occur if
   account authorization expires during a tool call?
6. Should this be split into stages: (A) identity-owned cart storage/build and
   catalog availability, then (B) confirmed placement into identity orders; or
   approve both together? A split reduces authorization and persistence risk.
7. Resolved split: Stage 4A covers persistent cart build; the user has now
   separately approved Stage 4B placement.

## Recommended staged path (approval required)

**Recommended first slice:** Stage 4A, account-only catalog access and
identity-scoped cart build/read, with cart lifetime explicitly selected,
backend price calculation, no placement, no fixture fallback, and fake-based
tests for identity isolation, invalid credentials, unknown/ambiguous products,
cart validation and totals. Do not add an inventory quantity/decrement because
stock is unlimited. Update tool/WebSocket/frontend-facing contracts only after
the user approves the exact slice.

Stage 4B is approved: account-only placement with fresh account authorization,
action-bound confirmation of exact cart/price details, single-use confirmation,
server price/policy revalidation, identity-owned order persistence, and
idempotent retry. A changed catalog price fails closed and requires a newly
built cart and fresh confirmation. Same-identity mutations are serialized
in-process. Tests must prove isolation, no order on staging/failure, correct
order ownership, repeat idempotency, cancellation compatibility, and safe
serialization. No payment provider, database, persistent real account, stock
decrement, or live Gemini call.

## Approval gate and progress record

This file is the dedicated Stage 4 audit/progress record. Stages 4A and 4B are
approved; any other follow-on work requires separate approval. At each
implementation stage, update this document with the design decision, exact
changed files, commands and test results, remaining risks, and approved/actual
real-provider run count. Current approved provider runs: **0**; actual calls:
**0**.

## Stage 4A implementation progress

- **Approval/design:** User approved catalog access and identity-owned carts
  that persist across calls for the same demo identity; order placement remains
  gated. No stock quantities/decrement, payment, fixture fallback, or real
  inventory service.
- **Implementation:** Complete. Account-mode WebSocket construction reloads
  carts from the authorized identity; account `build_order_cart` is dispatched
  through the existing canonical catalog/pricing service; resulting carts are
  saved back to that identity. `list_order_carts()` allows retrieval across
  calls. Mock DB behavior is unchanged.
- **Changed files:** `backend/app/domain/demo_sessions.py`,
  `backend/app/domain/orders.py`, `backend/app/main.py`,
  `backend/tests/test_demo_sessions.py`, `backend/tests/test_order_service.py`,
  `backend/tests/test_live.py`, `docs/aura_tool_call_list.md`,
  `docs/cart-order-tool-contract.md`, `docs/ws-event-contract.md`,
  `docs/frontend-demo-identity-handoff.md`, `docs/aria-capabilities-audit.md`,
  `docs/stage4-account-commerce-audit.md`.
- **Tests/results:** `cd backend && .venv/bin/pytest -q
  tests/test_demo_sessions.py tests/test_order_service.py tests/test_live.py -k
  'temporary_account_carts or account_carts_persist or
  carts_can_be_rehydrated or account_mode_guessed_mock_order_id'` → 4 passed,
  42 deselected, 1 warning. Full suite: `cd backend && .venv/bin/pytest -q` →
  148 passed, 2 warnings, 3 subtests passed. An earlier broader targeted run
  encountered a timing failure in unrelated
  `test_ws_startup_audio_is_held_fifo_and_oldest_frame_dropped`; the full suite
  passed afterward.
- **Remaining risks:** Same-identity concurrent cart/order snapshot updates are
  not transactional; cart/session data is process-local and disappears on
  restart or identity expiry. Cart construction returns the cart immediately;
  no separate cart-list tool was added. Placement remains gated pending Stage
  4B approval.
- **Provider runs:** approved 0; actual 0.

## Stage 4B implementation progress

- **Approval/design:** User approved simulated account placement from persistent
  account carts, existing action-bound confirmation, identity-owned order
  persistence, idempotent retries, in-process same-identity serialization, and
  current price revalidation. A changed price fails closed; a new cart and fresh
  confirmation are required. Payment and fulfilment remain out of scope.
- **Implementation:** Complete. Account tool execution now revalidates and
  serializes account state operations under the process-local session-store
  lock, rehydrates the latest carts/orders, and writes state back before
  releasing the lock. Placement follows the existing one-time confirmation
  protocol, validates current product prices and recomputes totals/policy, then
   writes a simulated Processing order to identity-owned state.
   Account-created orders use the currently authorized identity's display name
   as their customer label instead of the generic `Demo Customer` placeholder.
   The system prompt distinguishes `temporary_account` orders from Mock DB
   sample fixtures and forbids describing account-owned orders as unlinked.
  `list_order_carts()` lists only authorized persisted carts with a placement
  status. The Aria prompt directs it to discover existing carts from backend
  state instead of relying on cross-call provider memory. Changed prices return
  `CART_PRICE_CHANGED` without staging confirmation; callers must build a new
  cart and reconfirm. Placed-cart mapping and next order/cart sequences
  rehydrate so retries across calls are idempotent and IDs do not repeat.
- **Changed files:** `backend/app/domain/demo_sessions.py`,
  `backend/app/domain/orders.py`, `backend/app/main.py`,
  `backend/app/tools/registry.py`, `backend/tests/test_confirmations.py`,
  `backend/app/live/prompt.py`, `backend/tests/test_tool_registry.py`,
  `backend/tests/test_order_service.py`,
  `backend/tests/test_live.py`,
  `docs/aura_tool_call_list.md`, `docs/cart-order-tool-contract.md`,
  `docs/ws-event-contract.md`, `docs/frontend-demo-identity-handoff.md`,
  `docs/aria-capabilities-audit.md`, `docs/stage4-account-commerce-audit.md`.
- **Tests/results:** Targeted command `cd backend && .venv/bin/pytest -q
  tests/test_confirmations.py tests/test_order_service.py
  tests/test_tool_registry.py tests/test_demo_sessions.py tests/test_live.py -k
  'place_order or account_order_placement or account_carts_persist or
  account_mode_guessed_mock_order_id or carts_can_be_rehydrated or
  changed_catalog_price or temporary_account_carts'` → 8 passed, 62 deselected,
  1 warning. Cart discovery/placement integration:
  `cd backend && .venv/bin/pytest -q tests/test_live.py::test_account_carts_persist_across_calls_and_remain_identity_scoped tests/test_tool_registry.py::test_list_order_carts_exposes_persistent_candidates_and_current_price_status tests/test_live.py::test_account_order_placement_confirms_persists_and_retries_idempotently`
  → 3 passed, 1 warning. `cd backend && .venv/bin/pytest -q tests/test_tool_registry.py
  tests/test_live.py::test_ws_startup_audio_is_held_fifo_and_oldest_frame_dropped`
  → 18 passed, 2 warnings. Full suite: `cd backend && .venv/bin/pytest -q` →
  151 passed, 2 warnings, 3 subtests passed. `git diff --check` → clean. One
   intermediate full run encountered the timing-sensitive startup-audio test;
   it passed on its targeted rerun and the subsequent full run.
- **Follow-up correction:** Account placement now writes the authorized demo
  identity's display name to the created order; the prompt explicitly says
  `temporary_account` orders belong to that identity and reserves the
  “unlinked sample” disclaimer for Mock DB fixtures. Targeted tests:
  `cd backend && .venv/bin/pytest -q tests/test_live.py::test_account_order_placement_confirms_persists_and_retries_idempotently tests/test_live.py::test_prompt_contains_policy_boundaries_and_windows`
  → 2 passed, 1 warning. Latest full suite: 151 passed, 2 warnings,
  3 subtests passed.
- **Remaining risks:** Consent is interpreted by Gemini and is probabilistic;
  state remains in-memory/process-local. The session-store lock serializes all
  identities globally (safe but coarser than per-identity); multiple workers
  do not share state. No provider calls.
- **Provider runs:** approved 0; actual 0.
