# Cart and order tools — implementation contract

**Implementation contract, demo data, not given requirements.** This minimal
contract exists to support the documented tool names; it does not imply a real
catalog, checkout, payment, customer account, or order-management integration.

`backend/app/data/products.json` is the single source for five demo products.
It is read-only and loaded using a cached data access layer. Mock DB tool-created
carts/orders exist only in an `OrderService` instance (one instance per call);
process restart discards them. In account mode, Stage 4A carts are copied into
the owning temporary demo identity and reloaded on later calls for that identity.
They expire with the identity or are lost on process restart. Account carts do
not enter Mock DB state or another identity.

* `build_order_cart(items: [{product_id: string, quantity: integer}],
  payment_method: "COD" | "PREPAID")` accepts 1–10 distinct catalog products,
  quantity 1–10 each, and no extra fields. Product prices are server-owned.
  Shipping is ₹50 at or below ₹499 and free above ₹499. COD is allowed up to
   and including ₹2,500. A cart is returned with a session-local generated ID.
   In account mode, cart state persists across calls within that same temporary
   identity; in Mock DB mode, it remains call-scoped.
* `list_order_carts()` returns carts available in the active service. Account
  mode reads only the authorized identity's carts, including carts created in
  earlier calls. Each cart has `placement_status` of `ready`, `price_changed`,
  `unavailable`, or `placed`; changed/stale quotes must not be offered for
  placement. Mock DB mode only lists carts from the current call.
* `place_order(cart_id: string, confirmation_id?: string)` only accepts a cart
  from the same session. The first call without `confirmation_id` does not
  create an order; it returns `CONFIRMATION_REQUIRED` with a one-time
  `confirmation_id` bound to the exact cart contents, payment method, and total.
  Aria asks the customer to confirm those details and retries with the same
  `cart_id` plus that ID only after a clear affirmative in the immediately next
   user turn. The backend rechecks current catalog prices, recomputes cart totals,
   and rechecks COD eligibility before creating an order with Processing status.
   A changed catalog price fails with `CART_PRICE_CHANGED`; the customer must
   build a new cart and confirm its updated total. Confirmation IDs expire after the
  configured `PENDING_ACTION_TTL_SECONDS` (default 300 seconds) and are
  single-use. A repeated placement after successful completion returns the
   original order and marks `idempotent: true`; it does not create a second order.
   In account mode, placed orders persist with the owning temporary identity
   across calls and carry the authorized identity's display name as the customer
   label; Mock DB state remains call-scoped. This label is not authentication.
* `cancel_order(order_id: string, confirmation_id?: string)` follows the same
  two-call confirmation protocol, binding the pending request to the exact
  eligible order and its current items/status/total. Cancellation eligibility
  is rechecked by the order service at execution time.
* Both tools return `{"ok": true, ...}` on success or
  `{"ok": false, "error": {"code": string, "message": string}}` on failure.
  A successful cart includes `cart` with `cart_id`, `items`, `payment_method`,
  `subtotal_inr`, `shipping_fee_inr`, `total_inr`, and `cod_allowed`. A successful
  placement includes `order` and `idempotent`.

This is demo behavior only: no payment is collected, no external API is called,
and generated identifiers/state are temporary and process-local.
