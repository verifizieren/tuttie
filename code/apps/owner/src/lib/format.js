// Small helpers that turn the node's raw facts into text for the page.

export const chf = amount => (amount === undefined || amount === null ? "–" : `CHF ${amount}`);

/** Ids like "late-arrival-dog", "room_type" or "posting.created" as readable words. */
export const words = id => String(id).replace(/[-_.]/g, " ").replace(/^./, c => c.toUpperCase());

export function ago(timestamp, now) {
  const seconds = Math.max(0, Math.round((now - timestamp) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds} s ago`;
  return `${Math.round(seconds / 60)} min ago`;
}
