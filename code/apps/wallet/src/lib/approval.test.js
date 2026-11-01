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

// The server's decided event in its real shape (assistant/tools.py, the emit after approvals.wait):
// detail = { decision: <the signed decision, aps/approval.py sign_decision> }; only the pending
// event has detail.approval_id.
const signedDecision = (id, decision) => ({ approval_id: id, decision, action: "book", amount_chf: 128,
                                            decided_at: "2026-11-01T02:00:00Z", signature: "x" });
const decidedEvent = (step, id, status) => ({ step, kind: "approval", status, turn: "t1",
                                              detail: { decision: signedDecision(id, status) } });

test("the decision the server streamed belongs to its own approval only", async () => {
  const { applyEvent, startTurn, EMPTY } = await import("./activity.js");
  const { serverDecision } = await import("./approval.js");
  const pending = applyEvent(startTurn(EMPTY, "book"), { step: 1, kind: "approval", status: "pending", detail: { approval_id: "a1" } });
  assert.equal(serverDecision(pending, "a1"), null);
  const approved = applyEvent(pending, decidedEvent(2, "a1", "approved"));
  assert.equal(serverDecision(approved, "a1"), "approved");
  assert.equal(serverDecision(approved, "a2"), null);  // a late event never finishes a newer sheet
  assert.equal(serverDecision(approved, ""), null);
  const declined = applyEvent(pending, decidedEvent(2, "a1", "declined"));
  assert.equal(serverDecision(declined, "a1"), "declined");
  const expired = applyEvent(pending, { step: 2, kind: "approval", status: "expired", detail: {} });
  assert.equal(serverDecision(expired, "a1"), null);  // not a decision: the sheet's own call says what happened
  const odd = applyEvent(pending, { step: 2, kind: "approval", status: "approved", detail: { decision: { approval_id: { x: 1 } } } });
  assert.equal(serverDecision(odd, "a1"), null);
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

test("a sheet that is finishing stays until it is done, a newer approval comes after it", async () => {
  const { sheetOf } = await import("./approval.js");
  const a1 = { id: "a1" }, a2 = { id: "a2" };
  assert.equal(sheetOf(a2, a1), a1);    // the city tax waits behind the booking's checkmark
  assert.equal(sheetOf(a2, null), a2);
  assert.equal(sheetOf(null, a1), a1);
  assert.equal(sheetOf(null, null), null);
});

test("a tap counts only on a sheet that was on screen when the finger came down", async () => {
  const { tapAccepted, ARM_MS } = await import("./approval.js");
  const shownAt = 1000;
  // a click from code or the keyboard (detail 0) always counts: the keynote deck uses button.click()
  assert.equal(tapAccepted({ detail: 0, shownAt, downAt: null }), true);
  // a finger tap that started on the sheet before (the old sheet that slid away) never counts
  assert.equal(tapAccepted({ detail: 1, shownAt, downAt: null, now: shownAt + 200 }), false);
  assert.equal(tapAccepted({ detail: 1, shownAt, downAt: 900 }), false);
  // the finger came down while the sheet was still sliding in: aimed at what was there before
  assert.equal(tapAccepted({ detail: 1, shownAt, downAt: shownAt + ARM_MS - 1 }), false);
  assert.equal(tapAccepted({ detail: 1, shownAt, downAt: shownAt + ARM_MS }), true);
});

test("a tap without a pointerdown (VoiceOver, some assistive input) counts by its own time", async () => {
  const { tapAccepted, ARM_MS } = await import("./approval.js");
  const shownAt = 1000;
  // no pointerdown on this sheet: judged by when the click came, so a quick tap aimed at the old
  // sheet still never counts, while an assistive double tap on a settled sheet does
  assert.equal(tapAccepted({ detail: 1, shownAt, downAt: null, now: shownAt + 250 }), false);
  assert.equal(tapAccepted({ detail: 1, shownAt, downAt: null, now: shownAt + ARM_MS + 400 }), true);
});

test("the streamed decision finishes a sheet the user decided on, also after a timeout or a gone answer", async () => {
  const { finishesOn } = await import("./approval.js");
  assert.equal(finishesOn("approved", "sending", "approved"), true);
  assert.equal(finishesOn("approved", "ask", "approved"), true);     // after the 15 s timeout
  assert.equal(finishesOn("approved", "gone", "declined"), true);    // Decline at the retry: 404, yet it was approved
  assert.equal(finishesOn("approved", "ask", null), false);          // never tapped: nothing to finish here
  assert.equal(finishesOn(null, "sending", "approved"), false);
  assert.equal(finishesOn("approved", "scan", "approved"), false);   // not sent yet: the call says what happens
  assert.equal(finishesOn("approved", "done", "approved"), false);   // already finished
});
