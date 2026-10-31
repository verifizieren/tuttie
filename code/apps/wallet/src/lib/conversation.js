// Rebuild display state from the server's timeline; local history supplies user text only.
import { applyEvent, EMPTY } from "./activity.js";

export function restoreConversation(events, id, snapshot) {
  const same = snapshot?.id === id;
  const turns = same ? snapshot.turns.map(t => ({ said: t.said })) : [];
  const state = events.reduce(applyEvent, { ...EMPTY, id, turns });
  return same && snapshot.picked ? { ...state, picked: snapshot.picked } : state;
}
