// Rebuild display state from the server's timeline. Its "turn" events hold every request with
// its id, so turns, answers and bookings come back in place; a local snapshot only supplies the
// user's words for a timeline from before turns had ids.
import { applyEvent, EMPTY } from "./activity.js";

export function restoreConversation(events, id, snapshot) {
  const same = snapshot?.id === id;
  const serverTurns = events.some(e => e.kind === "turn");
  const turns = same && !serverTurns ? snapshot.turns.map(t => ({ said: t.said })) : [];
  // A goodbye in a loaded chat is over: only a live one closes the card (App.jsx).
  const state = { ...events.reduce(applyEvent, { ...EMPTY, id, turns }), closing: null, swipes: [] };
  return same && snapshot.picked ? { ...state, picked: snapshot.picked } : state;
}
