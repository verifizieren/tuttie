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
  if ([404, 409, 410].includes(error?.status)) {
    return { gone: true, message: "This approval was already decided or has expired." };
  }
  if (error?.status) return { gone: false, message: "Your decision could not be saved. Please try again." };
  return { gone: false, message: "Your decision could not be sent. Check your connection and try again." };
}
