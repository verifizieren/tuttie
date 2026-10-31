// Follows this browser's conversation with Tuttie: its timeline (GET /history, then the live
// Server-Sent Events at /events) folded into the wallet's view (lib/activity.js).
//
// Opening the wallet starts fresh: a conversation that already ended is archived on this
// device (lib/history.js) and the server forgets it; one still running (Tuttie working, an
// approval waiting) is picked up where it was. The stream replays the timeline on connect;
// those events were already folded from /history, so the first ones are skipped.
import { useEffect, useMemo, useReducer, useState } from "react";
import { applyEvent, EMPTY, finished, startTurn } from "../lib/activity.js";
import { resetConversation } from "../lib/api.js";
import { archive, loadCurrent, loadHistory, saveCurrent } from "../lib/history.js";

function reducer(state, action) {
  switch (action.type) {
    case "load": return action.state;
    case "reset": return EMPTY;
    case "say": return startTurn(state, action.said);
    case "pick": return { ...state, picked: action.nodeIds };
    default: return applyEvent(state, action.event);
  }
}

async function timeline() {
  try {
    const response = await fetch("/history");
    return response.ok ? await response.json() : [];
  } catch {
    return [];
  }
}

export default function useAgentStream() {
  const [state, dispatch] = useReducer(reducer, EMPTY);
  const [history, setHistory] = useState(loadHistory);

  useEffect(() => {
    let stream = null, closed = false;
    (async () => {
      const events = await timeline();
      const current = loadCurrent();
      let resumed = events.reduce(applyEvent, { ...EMPTY, id: current?.id || null, turns: current?.turns || [] });
      let replayed = events.length;
      if (!events.length || finished(resumed)) {
        if (events.length) {
          setHistory(archive(resumed));
          await resetConversation().catch(() => {});
        }
        resumed = EMPTY;
        replayed = 0;
      }
      if (closed) return;
      dispatch({ type: "load", state: resumed });
      stream = new EventSource("/events");
      stream.addEventListener("message", e => {
        if (replayed > 0) { replayed -= 1; return; }  // already folded from /history
        dispatch({ type: "event", event: JSON.parse(e.data) });
      });
      stream.addEventListener("reset", () => dispatch({ type: "reset" }));
    })();
    return () => { closed = true; stream?.close(); };
  }, []);

  // Keep what the server does not: this conversation's id and the user's own messages.
  useEffect(() => { saveCurrent(state); }, [state.id, state.turns.length]);  // eslint-disable-line react-hooks/exhaustive-deps

  const actions = useMemo(() => ({
    /** The user said something: a new turn in this conversation. */
    say: said => dispatch({ type: "say", said }),
    /** The user picked favourites from the cards. */
    pick: nodeIds => dispatch({ type: "pick", nodeIds }),
    /** Archive this conversation on the device and start a new one (the server forgets it). */
    newConversation: async snapshot => {
      if (snapshot.turns.length) setHistory(archive(snapshot));
      dispatch({ type: "reset" });
      await resetConversation().catch(() => {});
    },
  }), []);
  return [state, actions, history];
}
