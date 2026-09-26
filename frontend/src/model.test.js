import test from "node:test";
import assert from "node:assert/strict";
import { chartSegments, priceStatus, formatMoney } from "./model.js";

test("a missing observation is unknown, not a zero price deal", () => {
  assert.equal(priceStatus({ price: null, target_price: 500 }), "unknown");
  assert.equal(formatMoney(null), "Not checked");
});
test("old price is stale even when below target", () => {
  assert.equal(
    priceStatus(
      { price: 200, target_price: 500, fetched_at: "2020-01-01T00:00:00Z" },
      Date.parse("2026-09-26"),
    ),
    "stale",
  );
});
test("outages split the chart instead of inventing price continuity", () => {
  const points = [
    { price: 100, fetched_at: "2026-09-01T00:00:00Z" },
    { price: 90, fetched_at: "2026-09-01T12:00:00Z" },
    { price: 80, fetched_at: "2026-09-20T00:00:00Z" },
  ];
  assert.deepEqual(
    chartSegments(points).map((s) => s.length),
    [2, 1],
  );
});
test("no history stays empty", () => assert.deepEqual(chartSegments([]), []));
test("zero is a valid free price", () => assert.equal(formatMoney(0), "₹0"));

test("changed inputs invalidate pending search and workspace responses", async () => {
  const { createGeneration } = await import("./model.js");
  const gate = createGeneration();
  const old = gate.current();
  gate.advance();
  assert.equal(gate.isCurrent(old), false);
  assert.equal(gate.isCurrent(gate.current()), true);
});
