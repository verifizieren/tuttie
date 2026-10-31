// Follows this browser's conversation with Tuttie: its timeline (GET /history, then the live
// Server-Sent Events at /events) folded into the wallet's view (lib/activity.js).
//
// There is one conversation at a time. Opening the wallet picks it up only while it still
// runs (Tuttie working, an approval waiting); otherwise Tuttie starts fresh. The stream replays
// the timeline on connect; those events were already folded from /history, so they are skipped.
import { useEffect, useMemo, useReducer } from "react";
import { applyEvent, EMPTY, finished, startTurn } from "../lib/activity.js";
import { resetConversation } from "../lib/api.js";

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

  useEffect(() => {
    let stream = null, closed = false;
    (async () => {
      const events = await timeline();
      let resumed = events.reduce(applyEvent, EMPTY), replayed = events.length;
      if (events.length && finished(resumed)) {
        await resetConversation().catch(() => {});
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

  const actions = useMemo(() => ({
    /** The user said something: a new turn in this conversation. */
    say: said => dispatch({ type: "say", said }),
    /** The user liked some hotels on the cards. */
    pick: nodeIds => dispatch({ type: "pick", nodeIds }),
    /** Start a new conversation (the server forgets the current one). */
    newConversation: async () => {
      dispatch({ type: "reset" });
      await resetConversation().catch(() => {});
    },
  }), []);
  return [state, actions];
}
