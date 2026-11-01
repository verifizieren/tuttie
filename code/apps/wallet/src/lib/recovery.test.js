import assert from "node:assert/strict";
import test from "node:test";
import { BUSY_NOTE, clearsOnReconnect, lostOnRestart, MIC_BLOCKED_NOTE, micRefused, newChatFailure, PICK_UNREACHABLE, OFFLINE_NOTE, shouldResend, voiceNote,
         voiceRetryDelay } from "./recovery.js";

test("voice retries back off from 2 s and stop growing at 30 s", () => {
  assert.deepEqual([1, 2, 3, 4, 5, 6, 20].map(voiceRetryDelay), [2000, 4000, 8000, 16000, 30000, 30000, 30000]);
});

test("only a voice that cannot connect is named; text-only servers stay silent", () => {
  assert.equal(voiceNote("unavailable"), "Voice unavailable · tap to retry");
  for (const state of ["off", "connecting", "ready", "live", "disabled"]) assert.equal(voiceNote(state), "");
});

test("a blocked microphone is named first, except on a text-only server", () => {
  assert.equal(MIC_BLOCKED_NOTE, "Microphone blocked — type instead");
  for (const state of ["connecting", "ready", "live", "unavailable"]) assert.equal(voiceNote(state, true), MIC_BLOCKED_NOTE);
  assert.equal(voiceNote("disabled", true), "");
});

test("only the browser's microphone refusals count as blocked", () => {
  for (const name of ["NotAllowedError", "NotFoundError", "SecurityError", "PermissionDeniedError", "NotReadableError"]) {
    assert.equal(micRefused({ name }), true, name);
  }
  for (const error of [new TypeError("Failed to fetch"), { name: "AbortError" }, null, undefined, "NotAllowedError"]) {
    assert.equal(micRefused(error), false);
  }
});

test("messages are sent again only when the server was not reached or failed", () => {
  assert.equal(shouldResend(new TypeError("Failed to fetch")), true);
  assert.equal(shouldResend({ status: 502 }), true);
  assert.equal(shouldResend({ status: 409 }), false);
  assert.equal(shouldResend({ status: 400 }), false);
});

test("a busy Tuttie is a friendly note, other failures keep their reason", () => {
  assert.deepEqual(newChatFailure({ status: 409, message: "conversation is busy" }), { notice: BUSY_NOTE });
  assert.deepEqual(newChatFailure({ status: 500, message: "boom" }), { error: "boom" });
  assert.deepEqual(newChatFailure(new Error("Tuttie is unreachable right now")), { notice: OFFLINE_NOTE });
});

test("only an unreachable error goes by itself once the connection is back", () => {
  assert.equal(clearsOnReconnect("Tuttie is unreachable right now"), true);
  assert.equal(clearsOnReconnect(PICK_UNREACHABLE), true);
  assert.equal(clearsOnReconnect("The chat changed elsewhere. Showing the current one, please say it again."), false);
  assert.equal(clearsOnReconnect(""), false);
});

test("a chat the server lost while it still waited is noticed; a finished or other-tab chat is not", () => {
  const waiting = { id: "c1", turns: [{ id: "t1", said: "a room in Basel" }], cards: null, approval: null };
  const answered = { ...waiting, turns: [{ id: "t1", said: "hi", answer: "Hello" }] };
  assert.equal(lostOnRestart(waiting, "c1", "c2", []), true);
  assert.equal(lostOnRestart(waiting, "c1", "c1", []), false);  // the same chat: only caught up
  assert.equal(lostOnRestart(waiting, null, "c2", []), false);  // first load
  assert.equal(lostOnRestart(answered, "c1", "c2", []), false);  // done: just put away
  assert.equal(lostOnRestart({ ...answered, approval: { id: "a" } }, "c1", "c2", []), true);
  assert.equal(lostOnRestart({ ...answered, cards: [{ node_id: "h" }], picked: null }, "c1", "c2", []), true);
  assert.equal(lostOnRestart({ ...answered, cards: [{ node_id: "h" }], picked: ["h"] }, "c1", "c2", []), false);
  assert.equal(lostOnRestart(waiting, "c1", "c2", [{ id: "c1" }]), false);  // another tab moved on and archived it
  assert.equal(lostOnRestart({ id: "c1", turns: [] }, "c1", "c2", []), false);
});
