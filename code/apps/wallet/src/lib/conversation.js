// Rebuild display state from the server's timeline. Its "turn" events hold every request with
// its id, so turns, answers and bookings come back in place; a local snapshot only supplies the
// user's words for a timeline from before turns had ids, the hotel picked and how far the
// user swiped the cards (both happen only on this device).
import { applyEvent, EMPTY, validDeck } from "./activity.js";

export function restoreConversation(events, id, snapshot) {
  const same = snapshot?.id === id;
  const serverTurns = events.some(e => e.kind === "turn");
  const saved = same && !serverTurns && Array.isArray(snapshot.turns) ? snapshot.turns : [];
  const turns = saved.filter(t => typeof t?.said === "string").map(t => ({ said: t.said }));
  // A goodbye in a loaded chat is over: only a live one closes the card (App.jsx).
  const state = { ...events.reduce(applyEvent, { ...EMPTY, id, turns }), closing: null, swipes: [] };
  if (!same) return state;
  // The swipes so far live only on this device: continue the same deck where the user left it.
  // A stored deck in another shape is dropped: the user starts the cards again.
  const deck = validDeck(snapshot.deck) && snapshot.deck.step === state.cardsStep ? snapshot.deck : null;
  const picked = Array.isArray(snapshot.picked) && snapshot.picked.every(id => typeof id === "string") ? snapshot.picked : null;
  return { ...state, deck, ...(picked ? { picked } : {}) };
}
