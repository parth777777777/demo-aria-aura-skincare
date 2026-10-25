import test from "node:test";
import assert from "node:assert/strict";
import {
  getCustomerIntentLabel,
  getOrderCardData,
  getOrderIdLabel,
  getResolutionPill,
  getVisibleNotice,
} from "../src/lib/display.js";

test("maps all resolution statuses and falls back to no interaction", () => {
  assert.deepEqual(
    [
      "resolved",
      "not_eligible",
      "unresolved",
      "out_of_scope",
      "no_interaction",
    ].map((key) => getResolutionPill(key).label),
    [
      "Resolved",
      "Not eligible",
      "Unresolved",
      "Out of scope",
      "No interaction",
    ],
  );
  assert.equal(getResolutionPill("future").label, "No interaction");
});

test("maps all customer intents and preserves unknown values", () => {
  assert.deepEqual(
    [
      "order_status",
      "cancellation",
      "return",
      "damaged_product",
      "delivery_info",
      "place_order",
      "policy_question",
      "out_of_scope",
      "unclear",
    ].map(getCustomerIntentLabel),
    [
      "Order status",
      "Cancellation",
      "Return",
      "Damaged product",
      "Delivery info",
      "Place order",
      "Policy question",
      "Out of scope",
      "Unclear",
    ],
  );
  assert.equal(getCustomerIntentLabel("other"), "other");
});

test("labels null order IDs", () => {
  assert.equal(getOrderIdLabel(null), "No order mentioned");
  assert.equal(getOrderIdLabel("ORD-101"), "ORD-101");
});

test("shows recoverable notices until a call ends or transcript arrives, fatal notices always, and session limit notice", () => {
  const recoverable = { message: "Disconnected", recoverable: true };
  assert.equal(
    getVisibleNotice({ error: recoverable, status: { state: "live" } })
      .errorMessage,
    "Disconnected",
  );
  assert.equal(
    getVisibleNotice({
      error: recoverable,
      status: { state: "live" },
      turnCount: 1,
    }).errorMessage,
    null,
  );
  assert.equal(
    getVisibleNotice({ error: recoverable, status: { state: "ended" } })
      .errorMessage,
    null,
  );
  assert.equal(
    getVisibleNotice({
      error: { message: "Fatal", recoverable: false },
      status: { state: "live" },
      turnCount: 2,
    }).errorMessage,
    "Fatal",
  );
  assert.equal(
    getVisibleNotice({ status: { state: "ended", reason: "session_limit" } })
      .sessionLimit,
    true,
  );
});

test("derives order card fields only from successful detail results", () => {
  assert.deepEqual(
    getOrderCardData({
      name: "get_order_details",
      args: { order_id: "ORD-101" },
      result: {
        ok: true,
        order: {
          order_id: "ORD-101",
          status: "Shipped",
          items: [{ name: "Serum" }],
        },
      },
    }),
    { orderId: "ORD-101", status: "Shipped", items: "Serum" },
  );
  assert.equal(
    getOrderCardData({
      name: "get_order_details",
      args: { order_id: "ORD-101" },
      result: { ok: false, error: {} },
    }),
    null,
  );
  assert.equal(
    getOrderCardData({
      name: "get_order_details",
      args: { order_id: "ORD-101" },
    }),
    null,
  );
});
