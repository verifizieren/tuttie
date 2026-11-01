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
