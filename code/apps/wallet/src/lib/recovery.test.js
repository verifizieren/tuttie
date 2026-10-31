import assert from "node:assert/strict";
import test from "node:test";
import { BUSY_NOTE, newChatFailure, OFFLINE_NOTE, shouldResend, voiceNote, voiceRetryDelay } from "./recovery.js";

test("voice retries back off from 2 s and stop growing at 30 s", () => {
  assert.deepEqual([1, 2, 3, 4, 5, 6, 20].map(voiceRetryDelay), [2000, 4000, 8000, 16000, 30000, 30000, 30000]);
});

test("only a voice that cannot connect is named; text-only servers stay silent", () => {
  assert.equal(voiceNote("unavailable"), "Voice unavailable · tap to retry");
  for (const state of ["off", "connecting", "ready", "live", "disabled"]) assert.equal(voiceNote(state), "");
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
