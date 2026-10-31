// Tests for the approval sheet's wording and outcomes (lib/approval.js): `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { doneLabel, failureOf, recordedDecision, sendingLabel } from "./approval.js";

test("the pending and final words name the chosen decision", () => {
  assert.equal(sendingLabel("declined"), "Declining…");
  assert.equal(sendingLabel("approved"), "Approving…");
  assert.equal(doneLabel("declined"), "Declined");
  assert.equal(doneLabel("approved"), "Approved");
});

test("the server's signed decision wins over the tap", () => {
  assert.equal(recordedDecision({ decision: "declined" }, "approved"), "declined");
  assert.equal(recordedDecision({ decision: "approved" }, "declined"), "approved");
  assert.equal(recordedDecision({}, "declined"), "declined");
  assert.equal(recordedDecision(null, "approved"), "approved");
});

test("an approval that no longer waits is gone, not retried", () => {
  for (const status of [404, 409, 410]) {
    const failure = failureOf(Object.assign(new Error("x"), { status }));
    assert.equal(failure.gone, true);
    assert.match(failure.message, /already decided or has expired/);
  }
});

test("server errors and network errors can be retried", () => {
  const server = failureOf(Object.assign(new Error("x"), { status: 500 }));
  assert.equal(server.gone, false);
  assert.match(server.message, /try again/);
  const network = failureOf(new TypeError("Failed to fetch"));
  assert.equal(network.gone, false);
  assert.match(network.message, /connection/);
});
