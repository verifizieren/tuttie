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

test("the decision the server streamed belongs to its own approval only", async () => {
  const { applyEvent, startTurn, EMPTY } = await import("./activity.js");
  const { serverDecision } = await import("./approval.js");
  const pending = applyEvent(startTurn(EMPTY, "book"), { step: 1, kind: "approval", status: "pending", detail: { approval_id: "a1" } });
  assert.equal(serverDecision(pending, "a1"), null);
  const approved = applyEvent(pending, { step: 2, kind: "approval", status: "approved", detail: { approval_id: "a1" } });
  assert.equal(serverDecision(approved, "a1"), "approved");
  assert.equal(serverDecision(approved, "a2"), null);  // a late event never finishes a newer sheet
  const declined = applyEvent(pending, { step: 2, kind: "approval", status: "declined", detail: { approval_id: "a1" } });
  assert.equal(serverDecision(declined, "a1"), "declined");
  const expired = applyEvent(pending, { step: 2, kind: "approval", status: "expired", detail: { approval_id: "a1" } });
  assert.equal(serverDecision(expired, "a1"), null);  // not a decision: the sheet's own call says what happened
  const next = applyEvent(approved, { step: 3, kind: "approval", status: "pending", detail: { approval_id: "a2" } });
  assert.equal(serverDecision(next, "a2"), null);
});

test("a decision that gets no answer stops waiting and can be tried again", async () => {
  const { decide } = await import("./api.js");
  const saved = globalThis.fetch;
  let signal = null;
  globalThis.fetch = (_path, init) => new Promise((_resolve, reject) => {
    signal = init.signal;
    init.signal?.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
  });
  try {
    const error = await decide("a1", "approved", false, 30).then(() => null, e => e);
    assert.ok(error, "the call must not hang");
    assert.equal(signal.aborted, true);
    const failure = failureOf(error);
    assert.equal(failure.gone, false);
    assert.match(failure.message, /try again/);
    assert.doesNotMatch(failure.message, /abort|connection/i);
  } finally {
    globalThis.fetch = saved;
  }
});
