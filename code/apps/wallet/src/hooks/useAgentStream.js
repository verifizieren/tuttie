// Keep the active server conversation and its SSE stream together. Starting a new chat
// preserves the old assistant; resuming history restores its signed offers and agreements.
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { applyEvent, EMPTY, startTurn } from "../lib/activity.js";
import { newConversation, resumeConversation } from "../lib/api.js";
import { archive, loadCurrent, loadHistory, saveCurrent } from "../lib/history.js";
import { restoreConversation } from "../lib/conversation.js";

function reducer(state, action) {
  switch (action.type) {
    case "load": return action.state;
    case "reset": return { ...EMPTY, id: state.id };
    case "say": return startTurn(state, action.said);
    case "pick": return { ...state, picked: action.nodeIds };
    default: return applyEvent(state, action.event);
  }
}

async function timeline() {
  const response = await fetch("/history");
  if (!response.ok) throw new Error("Tuttie is unreachable right now");
  const id = response.headers.get("X-Conversation-ID");
  if (!id) throw new Error("The server needs an update before conversations can be resumed");
  return { events: await response.json(), id };
}

export default function useAgentStream() {
  const [state, rawDispatch] = useReducer(reducer, EMPTY);
  const lastChange = useRef("load");
  const dispatch = useCallback(action => { lastChange.current = action.type; rawDispatch(action); }, []);
  const [history, setHistory] = useState(loadHistory);
  const [switching, setSwitching] = useState(true);
  const [connectionError, setConnectionError] = useState("");
  const switchingRef = useRef(true);
  const stream = useRef(null);
  const activeId = useRef(null);
  const lastStep = useRef(0);
  const stateRef = useRef(state);
  stateRef.current = state;

  const connect = useCallback(() => {
    stream.current?.close();
    const source = new EventSource(`/events?conversation_id=${encodeURIComponent(activeId.current)}`);
    stream.current = source;
    source.addEventListener("message", e => {
      if (stream.current !== source) return;
      const event = JSON.parse(e.data);
      if (event.step <= lastStep.current) return;
      lastStep.current = event.step;
      dispatch({ type: "event", event });
    });
    source.addEventListener("reset", () => {
      if (stream.current !== source) return;
      lastStep.current = 0;
      dispatch({ type: "reset" });
    });
  }, [dispatch]);

  useEffect(() => {
    let closed = false;
    (async () => {
      try {
        const { events, id } = await timeline();
        if (closed) return;
        const current = loadCurrent();
        const snapshot = current?.id === id ? current : loadHistory().find(e => e.id === id)?.state;
        dispatch({ type: "load", state: restoreConversation(events, id, snapshot) });
        activeId.current = id;
        lastStep.current = events.at(-1)?.step || 0;
        connect();
      } catch (error) {
        if (!closed) setConnectionError(error.message);
      } finally {
        if (!closed) { switchingRef.current = false; setSwitching(false); }
      }
    })();
    return () => { closed = true; stream.current?.close(); stream.current = null; };
  }, [connect, dispatch]);

  // Never overwrite the saved chat with EMPTY before the initial history request returns.
  useEffect(() => {
    if (!switching && state.id) saveCurrent(state);
  }, [switching, state]);

  const actions = useMemo(() => {
    async function switchTo(snapshot, target) {
      if (switchingRef.current) throw new Error("Please wait for the conversation to load");
      switchingRef.current = true;
      setSwitching(true);
      stream.current?.close();
      stream.current = null;
      let verified = true;
      try {
        const { events, id } = await (target ? resumeConversation(target.id) : newConversation());
        // Never trust a browser snapshot as a source of booking authority: reload the
        // selected server timeline, while retaining only this device's user messages/pick.
        if (snapshot.turns.length) setHistory(archive(snapshot));
        dispatch({ type: "load", state: restoreConversation(events, id, target) });
        activeId.current = id;
        lastStep.current = events.at(-1)?.step || 0;
        setConnectionError("");
      } catch (error) {
        // The server may have switched even if its response was lost. Reconcile before
        // reconnecting, so the visible offer can never belong to a different chat.
        try {
          const { events, id } = await timeline();
          if (id !== snapshot.id) {
            if (snapshot.turns.length) setHistory(archive(snapshot));
            dispatch({ type: "load", state: restoreConversation(events, id, id === target?.id ? target : null) });
            activeId.current = id;
            lastStep.current = events.at(-1)?.step || 0;
          }
        } catch {
          verified = false;
          setConnectionError("Could not verify the active chat. Reload the wallet before continuing.");
        }
        throw error;
      } finally {
        if (verified) connect();
        switchingRef.current = false;
        setSwitching(false);
      }
    }
    return {
      say: said => dispatch({ type: "say", said }),
      pick: nodeIds => dispatch({ type: "pick", nodeIds }),
      newConversation: snapshot => switchTo(snapshot),
      resume: entry => switchTo(stateRef.current, entry.state),
    };
  }, [connect, dispatch]);
  return [state, actions, history, lastChange, switching, connectionError];
}
