// Follows the assistant's timeline (Server-Sent Events at /events) and folds every event into
// the wallet's view of the marketplace (lib/activity.js). A "reset" event starts over. On
// connect the stream replays the run so far, so a reloaded wallet shows everything again.
// `start()` clears the view when the user asks something new, before the first event arrives.
import { useEffect, useReducer } from "react";
import { applyEvent, EMPTY } from "../lib/activity.js";

function reducer(state, action) {
  if (action.type === "reset") return EMPTY;
  if (action.type === "start") return { ...EMPTY, phase: "thinking" };
  return applyEvent(state, action.event);
}

export default function useAgentStream() {
  const [state, dispatch] = useReducer(reducer, EMPTY);

  useEffect(() => {
    const stream = new EventSource("/events");
    stream.addEventListener("message", e => dispatch({ type: "event", event: JSON.parse(e.data) }));
    stream.addEventListener("reset", () => dispatch({ type: "reset" }));
    return () => stream.close();
  }, []);

  return [state, () => dispatch({ type: "start" })];
}
