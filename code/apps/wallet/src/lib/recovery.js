// How the wallet recovers from a failed request: when voice tries again, which messages are
// sent again on their own, and the friendly words for a refusal that is not really an error.

import { choosing } from "./activity.js";
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

/** The line under Tuttie's eyes while the microphone cannot be used. */
export const MIC_BLOCKED_NOTE = "Microphone blocked — type instead";

// getUserMedia's refusals: no permission (or a dismissed prompt, an insecure page), no
// microphone at all, or one held by another app. Older browsers use the Permission/Devices names.
const MIC_ERRORS = new Set(["NotAllowedError", "PermissionDeniedError", "PermissionDismissedError", "SecurityError",
                            "NotFoundError", "DevicesNotFoundError", "NotReadableError"]);

/** True when an error from opening the microphone means it cannot be used (blocked, missing,
 *  busy), not that the connection failed. */
export const micRefused = error => MIC_ERRORS.has(error?.name);

/** The line under Tuttie's eyes for the voice state, or "" when there is nothing to say.
 *  A blocked microphone (`micBlocked`) is named first: typing still works. A voice that should
 *  work but cannot connect is named too; a server without voice ("disabled") simply stays
 *  text-only. */
export function voiceNote(state, micBlocked = false) {
  if (state === "disabled") return "";
  if (micBlocked) return MIC_BLOCKED_NOTE;
  return state === "unavailable" ? "Voice unavailable · tap to retry" : "";
}

/** True when a failed message may be sent once more on its own: the server was not reached
 *  or failed itself (no status, 5xx). A refusal (4xx, e.g. 409 while Tuttie still works) is
 *  an answer and is never repeated. */
export function shouldResend(error) {
  return !error?.status || error.status >= 500;
}

/** The note after the server lost the chat on screen while it still waited for something. */
export const RESTART_NOTE = "Tuttie restarted — please ask again (the earlier chat is in History)";

/** True when the server now has another conversation (`id`) than the one on screen (`current`,
 *  connected as `activeId`) and the one on screen was not done: a question without an answer,
 *  an approval or hotel cards still waiting. That only happens when the server restarted (it
 *  keeps chats in memory): another tab cannot switch chats while one is busy, and a chat it
 *  left is already in the history (`saved`). A finished chat is simply put away, as before. */
export function lostOnRestart(current, activeId, id, saved) {
  if (!activeId || id === activeId || !current?.turns?.length) return false;
  if (saved.some(e => e.id === current.id)) return false;
  return current.turns.some(t => !t.answer) || Boolean(current.approval) || choosing(current);
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
