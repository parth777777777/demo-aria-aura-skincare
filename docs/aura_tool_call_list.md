# Aura Skincare — Tool Call List

## Gemini-callable tools
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

- `get_order_details(order_id: string)`
- `cancel_order(order_id: string)`
- `check_cancellation_eligibility(order_id: string)`
- `check_return_eligibility(order_id: string, customer_declared?: {unopened: boolean, unused: boolean, original_packaging: boolean})`
- `check_damaged_product_eligibility(order_id: string, customer_declared?: {hours_since_delivery?: number, has_photos?: boolean})`

All success results use `{"ok": true, ...}`; failures use
`{"ok": false, "error": {"code": string, "message": string}}`. Eligibility
results include `eligible: boolean | null`; missing customer declarations use
`reason: "NEEDS_CUSTOMER_CONFIRMATION"` and a `needed` list. Customer-declared
facts are explicitly labelled input and never override backend-owned order
status, amount, or recorded delivery age. Unknown tool arguments are rejected.

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
