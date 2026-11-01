// How the wallet recovers from a failed request: when voice tries again, which messages are
// sent again on their own, and the friendly words for a refusal that is not really an error.

import { UNREACHABLE } from "./api.js";

/** The error after a book choice that did not reach Tuttie (App.jsx pick). */
export const PICK_UNREACHABLE = "Tuttie could not be reached — swipe again to book";

/** True for an error that only says Tuttie could not be reached: it goes once the connection
 *  is back. Any other error (a refusal, the server's reason) stays until the next message. */
export const clearsOnReconnect = error => error === UNREACHABLE || error === PICK_UNREACHABLE;

const VOICE_RETRY_FIRST_MS = 2000;
const VOICE_RETRY_MAX_MS = 30000;

/** The wait before the next automatic voice join after `failures` failed ones in a row
 *  (1, 2, 3, ...): 2 s, 4 s, 8 s, ... up to 30 s. */
export function voiceRetryDelay(failures) {
  return Math.min(VOICE_RETRY_FIRST_MS * 2 ** Math.max(0, failures - 1), VOICE_RETRY_MAX_MS);
}

/** The line under Tuttie's eyes for the voice state, or "" when there is nothing to say.
 *  Only a voice that should work but cannot connect is named; a server without voice
 *  ("disabled") simply stays text-only. */
export function voiceNote(state) {
  return state === "unavailable" ? "Voice unavailable · tap to retry" : "";
}

/** True when a failed message may be sent once more on its own: the server was not reached
 *  or failed itself (no status, 5xx). A refusal (4xx, e.g. 409 while Tuttie still works) is
 *  an answer and is never repeated. */
export function shouldResend(error) {
  return !error?.status || error.status >= 500;
}

/** Tuttie is still working on an answer (HTTP 409): a new chat has to wait for it. */
export const BUSY_NOTE = "Tuttie is still working — new chat after this answer";

/** A "new chat" that did not reach the server: the wallet reconnects by itself, so this is
 *  only a passing note, never an error that outlives the connection coming back. */
export const OFFLINE_NOTE = "Tuttie is unreachable right now — try again in a moment";

/** The words for a failed "new chat": a busy Tuttie or a lost connection is a friendly note,
 *  anything else the server's reason. */
export function newChatFailure(error) {
  if (error?.status === 409) return { notice: BUSY_NOTE };
  if (!error?.status) return { notice: OFFLINE_NOTE };
  return { error: error?.message || "Tuttie is unreachable right now" };
}
