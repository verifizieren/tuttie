// Past conversations, kept on this device only (localStorage), newest first. A conversation is
// archived when the user starts a new chat, when Tuttie is opened again after being swiped down,
// or when another conversation is resumed from the history. The server retains the assistant
// in memory; the snapshot supplies the display and user messages when resuming it.
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
  // A conversation picked up after a reload may have no id yet: give it one, so it never replaces another.
  const id = state.id || `c-${Date.now().toString(36)}`;
  const entry = { id, at: Date.now(), title: state.turns[0].said, outcome: outcome(state), state };
  const list = [entry, ...loadHistory().filter(e => e.id !== id)].slice(0, MAX_ENTRIES);
  write(KEY, list);
  return list;
}

/** Remember the open conversation's id and turns (the server only keeps the timeline). */
export const saveCurrent = state => write(CURRENT, { id: state.id, turns: state.turns.map(t => ({ said: t.said })), picked: state.picked });

/** The open conversation's id and the user's messages, if the wallet was reloaded meanwhile. */
export const loadCurrent = () => read(CURRENT, null);

/** The line shown in the history when a past chat cannot be continued (lib/api.js errors carry
 *  the HTTP status): expired chats say so plainly, nothing silently starts elsewhere. */
export function resumeFailure(error) {
  if (error?.status === 404 || error?.status === 410) {
    return "This chat has expired and can no longer be continued. Start a new chat to check current offers.";
  }
  if (error?.status === 409) return error.message || "This chat cannot be continued right now.";
  return `Could not continue this chat: ${error?.message || "Tuttie is unreachable right now"}`;
}

/** The past chat open in the history that the keyboard should continue, if any: never the chat
 *  already on screen (`currentId`), and nothing while the list is shown (`openId` null). */
export const viewedChat = (entries, openId, currentId) =>
  (openId && openId !== currentId && entries.find(e => e.id === openId)) || null;
