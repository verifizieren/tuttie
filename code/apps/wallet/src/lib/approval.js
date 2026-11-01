// What the approval sheet shows while and after the user's decision travels to the assistant
// (code/assistant/app.py POST /approvals/{id}). Pure functions, tested in approval.test.js.

export const DECISIONS = ["approved", "declined"];

/** The words shown while a decision is being sent. */
export const sendingLabel = decision => (decision === "declined" ? "Declining…" : "Approving…");

/** The words next to the final mark. */
export const doneLabel = decision => (decision === "declined" ? "Declined" : "Approved");

/** The decision the server recorded: its signed answer is the truth, the user's tap only a fallback. */
export function recordedDecision(result, chosen) {
  return DECISIONS.includes(result?.decision) ? result.decision : chosen;
}

/** Why sending a decision failed, for the sheet. `gone` means the approval no longer waits
 *  (already decided, expired or unknown: 404, 409, 410), so retrying makes no sense. */
export function failureOf(error) {
  if (error?.timeout) return { gone: false, message: "Tuttie has not answered yet. Please try again." };
  if ([404, 409, 410].includes(error?.status)) {
    return { gone: true, message: "This approval was already decided or has expired." };
  }
  if (error?.status) return { gone: false, message: "Your decision could not be saved. Please try again." };
  return { gone: false, message: "Your decision could not be sent. Check your connection and try again." };
}

/** The decision the server streamed for approval `id` (its "approval" event), or null: a decision
 *  for another (older) approval, or an end that is not a decision (expired), never counts. */
export function serverDecision(state, id) {
  const decided = state?.decided;
  return id && decided?.id === id && DECISIONS.includes(decided.status) ? decided.status : null;
}

/** The approval the sheet shows: one that is finishing (the user decided, its final mark is still
 *  to be seen) comes first; a newer approval (e.g. the city tax right after a booking) follows
 *  once that sheet is done. */
export const sheetOf = (approval, finishing) => finishing || approval || null;

/** How long a sheet that just slid in ignores finger taps (its entry slide is 0.45 s). */
export const ARM_MS = 600;

/** Whether a click on a sheet's buttons counts. A click from code or the keyboard (`detail` 0)
 *  always does. A finger tap counts only if the finger came down on this sheet (`downAt`) once it
 *  had been on screen for ARM_MS (`shownAt`): a tap aimed at a sheet that just went never decides
 *  the one that took its place. Without a pointerdown, the click's own time counts. */
export function tapAccepted({ detail, shownAt, downAt, lastDown = pointer.lastDown, now = performance.now() }) {
  if (!detail) return true;
  if (downAt != null) return downAt - shownAt >= ARM_MS;
  // No pointerdown on this sheet. A finger that came down shortly before it showed (on the sheet
  // that went) and lifts over it now never counts; with no pointerdown at all (VoiceOver and some
  // assistive input send only the click), the click's own time is judged.
  if (lastDown != null && lastDown > shownAt - HELD_MS) return false;
  return now - shownAt >= ARM_MS;
}

/** How long before a sheet showed a pointerdown elsewhere still counts as a press held across it. */
const HELD_MS = 2000;

/** The last pointerdown anywhere on the page (capture phase), for tapAccepted. */
export const pointer = { lastDown: null };
if (typeof document !== "undefined") {
  document.addEventListener("pointerdown", () => { pointer.lastDown = performance.now(); }, { capture: true });
}

/** Whether the decision the server streamed (`recorded`) finishes the sheet now: only once the
 *  user decided here (`decision`) and the call was sent, also when it then timed out (back to
 *  "ask") or came back as no longer waiting ("gone"); the server's record decides the mark. */
export const finishesOn = (recorded, stage, decision) =>
  Boolean(recorded && decision && ["sending", "ask", "gone"].includes(stage));
