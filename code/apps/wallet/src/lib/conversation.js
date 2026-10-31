// Rebuild display state from the server's timeline. Its "turn" events hold every request with
// its id, so turns, answers and bookings come back in place; a local snapshot only supplies the
// user's words for a timeline from before turns had ids, the hotel picked and how far the
// user swiped the cards (both happen only on this device).
import { applyEvent, EMPTY } from "./activity.js";

export function restoreConversation(events, id, snapshot) {
  const same = snapshot?.id === id;
  const serverTurns = events.some(e => e.kind === "turn");
  const turns = same && !serverTurns ? snapshot.turns.map(t => ({ said: t.said })) : [];
  // A goodbye in a loaded chat is over: only a live one closes the card (App.jsx).
  const state = { ...events.reduce(applyEvent, { ...EMPTY, id, turns }), closing: null, swipes: [] };
  if (!same) return state;
  // The swipes so far live only on this device: continue the same deck where the user left it.
  const deck = snapshot.deck?.step === state.cardsStep ? snapshot.deck : null;
  return { ...state, deck, ...(snapshot.picked ? { picked: snapshot.picked } : {}) };
}
