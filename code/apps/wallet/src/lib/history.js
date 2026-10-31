// Past conversations, kept on this device only (localStorage), newest first. A conversation is
// archived when the user swipes left for a new one, or when the wallet opens again after it
// finished. The server forgets it then (POST /reset); the wallet keeps what it showed.
// Storage can be missing or full (private mode): then history simply stays empty.

const KEY = "tuttie.history";
const CURRENT = "tuttie.current";  // the open conversation's own parts the server does not keep
const MAX_ENTRIES = 30;

function read(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch { /* storage unavailable: nothing to keep */ }
}

/** All archived conversations, newest first. */
export const loadHistory = () => read(KEY, []);

/** A short line for the list: the booking, or the start of Tuttie's last answer. */
function outcome(state) {
  if (state.booking) return `Booked ${state.booking.hotel} · CHF ${state.booking.total}`;
  const last = [...state.turns].reverse().find(t => t.answer)?.answer || "";
  return last.replace(/\*\*/g, "").replace(/\s*\[\d+\]/g, "").split(/(?<=[.!?])\s/)[0].slice(0, 90);
}

/** Archive a conversation (replacing an earlier copy of the same one); returns the new list. */
export function archive(state) {
  if (!state.turns.length) return loadHistory();
  const entry = { id: state.id, at: Date.now(), title: state.turns[0].said, outcome: outcome(state), state };
  const list = [entry, ...loadHistory().filter(e => e.id !== state.id)].slice(0, MAX_ENTRIES);
  write(KEY, list);
  return list;
}

/** Remember the open conversation's id and turns (the server only keeps the timeline). */
export const saveCurrent = state => write(CURRENT, { id: state.id, turns: state.turns.map(t => ({ said: t.said })) });

/** The open conversation's id and the user's messages, if the wallet was reloaded meanwhile. */
export const loadCurrent = () => read(CURRENT, null);
