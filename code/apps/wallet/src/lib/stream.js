// Keeping the wallet in step with the server's timeline when the event stream (GET /events)
// drops. Every event has a step number (1, 2, 3 ... per conversation, documentation/formats.md),
// so after a gap GET /history says exactly what was missed. Pure functions; the hook
// (hooks/useAgentStream.js) does the fetching and reconnecting.

/** How to catch up from the server's timeline (`events`, conversation `id`), given the
 *  conversation on screen and the last step it applied:
 *  { reload: true } when the screen cannot simply continue (another conversation, or a timeline
 *  that was reset or restarted meanwhile), else { reload: false, missed: [events after it] }. */
export function catchUp(events, id, activeId, lastStep) {
  if (!activeId || id !== activeId) return { reload: true };
  if (lastStep > 0 && events[lastStep - 1]?.step !== lastStep) return { reload: true };
  return { reload: false, missed: events.filter(e => e.step > lastStep) };
}

/** Wait before reconnect attempt `n` (0, 1, 2 ...): quick at first, then every 10 s. */
export const retryDelay = n => Math.min(10000, 500 * 2 ** n);

/** After this many failed attempts in a row the wallet says it is offline, not just reconnecting. */
export const OFFLINE_AFTER = 3;

/** The line under Tuttie's eyes for the stream's state ("" while it is live). */
export const linkStatus = link => ({ reconnecting: "Reconnecting…", offline: "Connection lost · retrying" }[link] || "");
