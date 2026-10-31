// React side of Tuttie's presence (lib/presence.js): what Tuttie is doing, for its eyes.
//
// App creates the presence once with usePresenceSource and feeds it (mode, conversation,
// error, dragged card, voice levels); everything below App reads it through the context:
//
//   const { state, detail, since } = usePresenceState();   // re-renders only when the state changes
//   usePresenceEvents(event => { ... });                    // every signal, no re-render:
//       { type: "state", state, detail, since } | { type: "levels", speaking, hearing } | { type: "cue", name, detail }
//
// The face gets the same signals without any React: if the TuttieFace instance has an
// `onPresence(event)` method, it is called for every event (see lib/face.js).
import { createContext, useContext, useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { createPresence, cuesBetween } from "../lib/presence.js";

const PresenceContext = createContext(null);
export const PresenceProvider = PresenceContext.Provider;

/**
 * Create and feed the presence (call once, in App).
 * @param inputs { mode, agent, error, lean, lastChange }: the wallet's current values; lastChange is
 *               useAgentStream's ref to the latest change's kind (no cues for "load" / "reset")
 * @param face   ref to the face instance; gets every event at face.current.onPresence(event) if defined
 * @returns the presence: pass it to <PresenceProvider value={presence}>; call presence.levels(s, h)
 *          with the voice levels and presence.cue(name) for the user's own moments (tap, new_chat)
 */
export function usePresenceSource({ mode, agent, error, lean, lastChange }, face) {
  const presence = useMemo(() => createPresence(), []);
  const lastAgent = useRef(agent);
  const lastMode = useRef(mode);

  // The face hears everything, if it wants to.
  useEffect(() => presence.subscribe(event => face?.current?.onPresence?.(event)), [presence, face]);

  // Cues from the conversation: compare it with the last one the presence saw.
  useEffect(() => {
    const before = lastAgent.current;
    lastAgent.current = agent;
    // A loaded or cleared conversation is a new start, not a series of moments to react to.
    const live = !["load", "reset"].includes(lastChange?.current);
    if (before !== agent && live) cuesBetween(before, agent).forEach(c => presence.cue(c.name, c.detail));
    presence.update({ agent });
  }, [agent, presence, lastChange]);

  useEffect(() => {
    const before = lastMode.current;
    lastMode.current = mode;
    if (before === "closed" && mode !== "closed") presence.cue("wake");
    if (before !== "closed" && mode === "closed") presence.cue("sleep");
    presence.update({ mode });
  }, [mode, presence]);

  useEffect(() => { presence.update({ error }); }, [error, presence]);
  useEffect(() => { presence.update({ lean }); }, [lean, presence]);
  return presence;
}

function usePresence() {
  const presence = useContext(PresenceContext);
  if (!presence) throw new Error("usePresence needs a <PresenceProvider> (App provides it)");
  return presence;
}

/** What Tuttie is doing: { state, detail, since }; re-renders only when it changes. */
export function usePresenceState() {
  const presence = usePresence();
  return useSyncExternalStore(
    notify => presence.subscribe(event => event.type === "state" && notify()),
    presence.current,
  );
}

/** Every presence signal (state, levels, cues) to `handler`, without re-rendering. */
export function usePresenceEvents(handler) {
  const presence = usePresence();
  const latest = useRef(handler);
  latest.current = handler;
  useEffect(() => presence.subscribe(event => latest.current(event)), [presence]);
}

/** The current state name only, e.g. for a CSS class: "speaking", "searching", ... */
export function usePresenceName() {
  return usePresenceState().state;
}

// Re-exported so components need only this module.
export { STATES, CUES } from "../lib/presence.js";
