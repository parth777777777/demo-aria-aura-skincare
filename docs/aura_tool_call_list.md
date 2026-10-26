# Aura Skincare — Tool Call List

## Gemini-callable tools
- `list_orders`
- `resolve_order_reference`
- `get_order_details`
- `check_cancellation_eligibility`
- `check_return_eligibility`
- `check_damaged_product_eligibility`
- `build_order_cart`
- `place_order`
- `cancel_order`

## Implementation contract (not given requirements)

The source requirements list these tool names but do not define argument
schemas or exact result structures. This milestone defines the following
Gemini-callable contracts:

- `list_orders()`
- `resolve_order_reference(reference: string)`
- `get_order_details(order_id: string)`
- `cancel_order(order_id: string, confirmation_id?: string)`
- `check_cancellation_eligibility(order_id: string)`
- `check_return_eligibility(order_id: string, customer_declared?: {unopened: boolean, unused: boolean, original_packaging: boolean})`
- `check_damaged_product_eligibility(order_id: string, customer_declared?: {hours_since_delivery?: number, has_photos?: boolean})`

All success results use `{"ok": true, ...}`; failures use
`{"ok": false, "error": {"code": string, "message": string}}`. Eligibility
results include `eligible: boolean | null`; missing customer declarations use
`reason: "NEEDS_CUSTOMER_CONFIRMATION"` and a `needed` list. Customer-declared
facts are explicitly labelled input and never override backend-owned order
status, amount, or recorded delivery age. Unknown tool arguments are rejected.

`list_orders()` returns the full candidate set authorized for the active mode.
In Mock DB mode this is all three sample fixtures, explicitly labeled as sample
demo orders rather than the caller's personal orders. In account mode it is
limited to the temporary identity's own orders (currently empty until account
order creation is implemented). `resolve_order_reference(reference)` returns
`match_status` of `matched`, `ambiguous`, `not_found`, or `needs_clarification`.
Only a unique match includes the full `order`; ambiguity returns clarification
summaries and never selects a target. Matching is deterministic over the
mode-authorized candidate set. Structured `last_order_id` context is scoped to
the Mock DB context token or account identity; no transcript is retained.

- `place_order(cart_id: string, confirmation_id?: string)`

For `cancel_order` and `place_order`, the first call omits `confirmation_id` and
only stages a pending action. The backend returns a one-time ID bound to the
exact action, target, current order/cart details, and user turn. After Aria
asks for confirmation, a clear affirmative in the immediately following
customer turn permits retrying the same tool with the same target and returned
`confirmation_id`. It expires after the configured
`PENDING_ACTION_TTL_SECONDS` (default 300 seconds), is single-use, and is
invalidated by a changed action/target or changed details. A stale, mismatched,
expired, or same-turn confirmation never executes. Gemini interprets the spoken
reply; the backend enforces the binding and lifecycle, but cannot deterministically
prove that model interpretation matches customer intent. Ambiguous replies must
fail closed.

`build_order_cart` and `place_order` use the implementation-only demo contract
in `docs/cart-order-tool-contract.md`; these are not given requirements.

`cancel_order` only changes the in-memory mock state belonging to the current
session. It is not a real cancellation transaction.

## Internal backend functions
- `can_cancel_order`
- `evaluate_return_eligibility`
- `evaluate_damage_claim`
- `generate_call_summary`
- `validate_call_summary`
- `build_transcript`
