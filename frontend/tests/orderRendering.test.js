import test from "node:test";
import assert from "node:assert/strict";
import { getOrderDisplays } from "../src/lib/orderRendering.js";

const order = (id) => ({
  order_id: id,
  items: ["Serum"],
  status: "Processing",
});
const tool = (name, result) => ({ name, result });

test("single detail and matched reference results produce one card each", () => {
  assert.equal(
    getOrderDisplays([
      tool("get_order_details", { ok: true, order: order("A") }),
    ]).length,
    1,
  );
  assert.equal(
    getOrderDisplays([
      tool("resolve_order_reference", {
        ok: true,
        match_status: "matched",
        order: order("B"),
      }),
    ])[0].id,
    "B",
  );
  assert.deepEqual(
    getOrderDisplays([
      tool("resolve_order_reference", {
        ok: true,
        match_status: "ambiguous",
        order: order("C"),
      }),
    ]),
    [],
  );
});

test("list results produce multiple unique cards and an empty result produces none", () => {
  const cards = getOrderDisplays([
    tool("list_orders", { ok: true, orders: [order("A"), order("B")] }),
  ]);
  assert.deepEqual(
    cards.map(({ id }) => id),
    ["A", "B"],
  );
  assert.deepEqual(
    getOrderDisplays([tool("list_orders", { ok: true, orders: [] })]),
    [],
  );
  assert.deepEqual(
    getOrderDisplays([
      tool("list_orders", { ok: true, orders: [order("A")] }),
      tool("get_order_details", { ok: true, order: order("A") }),
    ]).map(({ id }) => id),
    ["A"],
  );
});

test("only Mock DB cards are marked sample demo orders", () => {
  const mock = getOrderDisplays([
    tool("list_orders", {
      ok: true,
      source: "mock_db_sample_data",
      orders: [order("M")],
    }),
  ])[0];
  const account = getOrderDisplays([
    tool("list_orders", {
      ok: true,
      source: "temporary_account",
      orders: [order("T")],
    }),
  ])[0];
  assert.equal(mock.source, "mock_db_sample_data");
  assert.equal(account.source, "temporary_account");
});
