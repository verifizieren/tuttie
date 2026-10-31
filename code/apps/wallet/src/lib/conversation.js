// Rebuild display state from the server's timeline; local history supplies user text only.
import { applyEvent, EMPTY } from "./activity.js";

export function restoreConversation(events, id, snapshot) {
  const same = snapshot?.id === id;
  const turns = same ? snapshot.turns.map(t => ({ said: t.said })) : [];
  // A goodbye in a loaded chat is over: only a live one closes the card (App.jsx).
  const state = { ...events.reduce(applyEvent, { ...EMPTY, id, turns }), closing: null };
  return same && snapshot.picked ? { ...state, picked: snapshot.picked } : state;
}
