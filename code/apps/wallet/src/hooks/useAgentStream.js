// Keep the active server conversation and its SSE stream together. Starting a new chat
// preserves the old assistant; resuming history restores its signed offers and agreements.
// The stream can drop (network, phone asleep, server restart): the wallet then says so, keeps
// reconnecting and first catches up on what it missed from GET /history (lib/stream.js), so an
// answer the server finished meanwhile still shows up.
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { applyEvent, bindTurn, dropTurn, EMPTY, startTurn, withDeck } from "../lib/activity.js";
import { catchUp, OFFLINE_AFTER, retryDelay } from "../lib/stream.js";
import { newConversation, resumeConversation, UNREACHABLE } from "../lib/api.js";
import { archive, CURRENT_KEY, HISTORY_KEY, loadCurrent, loadHistory, saveCurrent } from "../lib/history.js";
import { restoreConversation } from "../lib/conversation.js";

function reducer(state, action) {
  switch (action.type) {
    case "load": return action.state;
    case "reset": return { ...EMPTY, id: state.id };
    case "say": return startTurn(state, action.said);
    case "pick": return { ...state, picked: action.nodeIds };
    case "bind": return bindTurn(state, action.said, action.turnId);
    case "drop": return dropTurn(state, action.said);
    case "deck": return withDeck(state, action.progress);
    default: return applyEvent(state, action.event);
  }
}

const CHECK_MS = 10000;  // while an answer is awaited, also compare with GET /history this often

async function timeline() {
  const response = await fetch("/history").catch(() => null);
  if (!response?.ok) throw new Error(UNREACHABLE);
  const id = response.headers.get("X-Conversation-ID");
  if (!id) throw new Error("The server needs an update before conversations can be resumed");
  const events = await response.json().catch(() => null);
  if (!Array.isArray(events)) throw new Error(UNREACHABLE);  // e.g. a proxy's error page
  return { events, id };
}

export default function useAgentStream() {
  const [state, rawDispatch] = useReducer(reducer, EMPTY);
  const lastChange = useRef("load");
  const dispatch = useCallback(action => { lastChange.current = action.type; rawDispatch(action); }, []);
  const [history, setHistory] = useState(loadHistory);
  const [switching, setSwitching] = useState(true);
  const [connectionError, setConnectionError] = useState("");
  const [link, setLink] = useState("live");  // the event stream: live | reconnecting | offline
  const switchingRef = useRef(true);
  const stream = useRef(null);
  const activeId = useRef(null);
  const lastStep = useRef(0);
  const retry = useRef({ timer: null, attempt: 0 });
  const stateRef = useRef(state);
  stateRef.current = state;

  // Bring the screen up to the server's timeline: apply the events it missed, or load the
  // conversation the server has now (first load, another tab started a new chat, a server
  // restart). Returns true if it loaded a timeline instead of continuing the one on screen.
  async function resync() {
    const { events, id } = await timeline();
    const plan = catchUp(events, id, activeId.current, lastStep.current);
    if (!plan.reload) {
      for (const event of plan.missed) {
        lastStep.current = event.step;
        dispatch({ type: "event", event });
      }
      return false;
    }
    const current = stateRef.current;
    const saved = loadHistory();
    // The chat on screen was left behind (e.g. by another tab, which archived it already).
    if (activeId.current && id !== activeId.current && current.turns.length && !saved.some(e => e.id === current.id)) {
      setHistory(archive(current));
    } else {
      setHistory(saved);
    }
    const local = loadCurrent();
    const snapshot = current.id === id ? current : local?.id === id ? local : saved.find(e => e.id === id)?.state;
    dispatch({ type: "load", state: restoreConversation(events, id, snapshot) });
    activeId.current = id;
    lastStep.current = events.at(-1)?.step || 0;
    return true;
  }

  function connect() {
    clearTimeout(retry.current.timer);
    stream.current?.close();
    const source = new EventSource(`/events?conversation_id=${encodeURIComponent(activeId.current)}`);
    stream.current = source;
    source.addEventListener("open", () => {
      if (stream.current !== source) return;
      retry.current.attempt = 0;
      setLink("live");
    });
    // The browser's own retry would replay the timeline without noticing a reset or another
    // conversation: close it and reconnect through GET /history instead.
    source.addEventListener("error", () => {
      if (stream.current !== source) return;
      retry.current.attempt += 1;
      reconnect();
    });
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
  }

  // Catch up and reconnect, after a short wait (`now`: at once), until it works.
  function reconnect(now = false) {
    clearTimeout(retry.current.timer);
    stream.current?.close();
    stream.current = null;
    setLink(retry.current.attempt >= OFFLINE_AFTER ? "offline" : "reconnecting");
    retry.current.timer = setTimeout(async () => {
      if (switchingRef.current) return;  // switching chats connects by itself
      try {
        await resync();
        if (switchingRef.current) return;
        setConnectionError("");
        connect();
      } catch {
        retry.current.attempt += 1;
        reconnect();
      }
    }, now ? 0 : retryDelay(retry.current.attempt));
  }

  // A quiet check while the stream looks fine: a connection can die without an error (a phone
  // asleep), and then a finished answer would never arrive.
  async function check() {
    if (switchingRef.current || !activeId.current || !stream.current) return;
    try {
      if (await resync()) connect();
    } catch { /* unreachable for now: the stream's own error starts reconnecting */ }
  }

  const live = useRef(null);
  live.current = { resync, connect, reconnect, check };

  useEffect(() => {
    let closed = false;
    (async () => {
      try {
        await live.current.resync();
        if (!closed) live.current.connect();
      } catch (error) {
        // Sending stays off while this shows; reconnecting clears it once the server answers.
        if (!closed) { setConnectionError(error.message); live.current.reconnect(); }
      } finally {
        if (!closed) { switchingRef.current = false; setSwitching(false); }
      }
    })();
    const wake = () => {
      if (document.visibilityState !== "visible" || switchingRef.current) return;
      if (stream.current) return live.current.check();
      retry.current.attempt = 0;
      live.current.reconnect(true);
    };
    // Another tab of this wallet started or resumed a chat: the server now has that one.
    const storage = e => {
      if (e.key === HISTORY_KEY) setHistory(loadHistory());
      if (e.key !== CURRENT_KEY || switchingRef.current || !activeId.current) return;
      let id = null;
      try { id = JSON.parse(e.newValue)?.id; } catch { /* not ours */ }
      if (id && id !== activeId.current) live.current.reconnect(true);
    };
    document.addEventListener("visibilitychange", wake);
    window.addEventListener("online", wake);
    window.addEventListener("storage", storage);
    return () => {
      closed = true;
      clearTimeout(retry.current.timer);
      stream.current?.close();
      stream.current = null;
      document.removeEventListener("visibilitychange", wake);
      window.removeEventListener("online", wake);
      window.removeEventListener("storage", storage);
    };
  }, []);

  // While a request waits for its answer, look at GET /history now and then as well.
  const waiting = state.turns.some(t => t.id && !t.answer);
  useEffect(() => {
    if (!waiting) return undefined;
    const timer = setInterval(() => live.current.check(), CHECK_MS);
    return () => clearInterval(timer);
  }, [waiting]);

  // Never overwrite the saved chat with EMPTY before the initial history request returns.
  useEffect(() => {
    if (!switching && state.id) saveCurrent(state);
  }, [switching, state]);

  const actions = useMemo(() => {
    async function switchTo(snapshot, target) {
      if (switchingRef.current) throw new Error("Please wait for the conversation to load");
      switchingRef.current = true;
      setSwitching(true);
      clearTimeout(retry.current.timer);
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
          // Unreachable (e.g. offline for a moment): keep trying in the background; the first
          // GET /history that works loads whichever chat the server has and clears this.
          verified = false;
          setConnectionError("Tuttie is unreachable right now · retrying");
        }
        throw error;
      } finally {
        switchingRef.current = false;
        setSwitching(false);
        if (verified) live.current.connect();
        else { retry.current.attempt = 0; live.current.reconnect(); }
      }
    }
    return {
      say: said => dispatch({ type: "say", said }),
      // POST /chat accepted the message as this turn; make sure its answer can arrive.
      sent: (said, turnId) => {
        dispatch({ type: "bind", said, turnId });
        if (!stream.current && !switchingRef.current) live.current.reconnect(true);
      },
      // POST /chat failed: the message is no turn. 409 = the server is on another chat now.
      failed: (said, error) => {
        dispatch({ type: "drop", said });
        if (error?.status === 409 && !switchingRef.current) live.current.reconnect(true);
      },
      // The user acts while the stream is down: try to reconnect now instead of waiting.
      retry: () => {
        if (stream.current || switchingRef.current) return;
        retry.current.attempt = 0;
        live.current.reconnect(true);
      },
      pick: nodeIds => dispatch({ type: "pick", nodeIds }),
      deck: progress => dispatch({ type: "deck", progress }),
      newConversation: snapshot => switchTo(snapshot),
      resume: entry => switchTo(stateRef.current, entry.state),
    };
  }, [dispatch]);
  return [state, actions, history, lastChange, switching, connectionError, link];
}
