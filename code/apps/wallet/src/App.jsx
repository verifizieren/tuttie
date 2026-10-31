// The wallet screen: two generic bank cards and the Tuttie card, which is the agent's face.
//
// The agent has three modes:
//   closed  card in the stack, eyes closed (asleep)
//   voice   card open, eyes open; this is the main interface and stays on until the user
//           swipes the card down or switches to typing; taps never send Tuttie away
//   typing  card open with a text field; the eyes close while the user types
//
// Text goes to Tuttie (POST /chat); in voice mode the user simply talks (hooks/useVoice.js,
// code/voice) and Tuttie answers aloud, its answer appearing word by word as it speaks. After a
// typed message Tuttie stays quiet (text only) until the user taps its face or the mic button. What Tuttie does on the agent web arrives on the event
// stream and is shown under its eyes (Activity), including the approval sheet.
//
// There is one conversation at a time: once the user swipes Tuttie down, the next opening
// starts a fresh one (unless an approval still waits for the user). The dock under the open
// card shows earlier conversations (kept on this device), starts a new one, or switches to typing.
//
// Tuttie's presence (hooks/usePresence.js) folds all of this into one signal for the eyes: what
// Tuttie is doing (speaking, listening, searching, negotiating, ...), the voice levels and
// one-off cues (an offer, an agreement, a blocked scam). Components below read it with
// usePresenceState / usePresenceEvents; the face gets it at face.onPresence(event) if defined.
import { useEffect, useRef, useState } from "react";
import Activity from "./components/Activity.jsx";
import AgentCard from "./components/AgentCard.jsx";
import ApprovalSheet from "./components/ApprovalSheet.jsx";
import BankCard from "./components/BankCard.jsx";
import Dock from "./components/Dock.jsx";
import History from "./components/History.jsx";
import useAgentStream from "./hooks/useAgentStream.js";
import useFace from "./hooks/useFace.js";
import { PresenceProvider, useFaceDirector, usePresenceSource } from "./hooks/usePresence.js";
import useVisibleViewport from "./hooks/useVisibleViewport.js";
import useVoice from "./hooks/useVoice.js";
import { sendChat } from "./lib/api.js";
import { currentTask } from "./lib/activity.js";
import { resumeFailure, viewedChat } from "./lib/history.js";

// Taps on the controls right after opening are ignored, so the tap that opens the card can
// never land on the keyboard icon.
const OPEN_GUARD_MS = 700;
const REVEAL_WAIT_MS = 3000;  // no speech for a new answer by then: show it in full at once
const CLOSE_AFTER_MS = 900;  // after the goodbye: a moment to read it before the card closes

export default function App() {
  const [mode, setMode] = useState("closed");
  const [error, setError] = useState("");  // the only text under the eyes: Tuttie cannot be reached
  const canvas = useRef(null);
  const openedAt = useRef(0);
  const closedOnce = useRef(false);  // the user swiped Tuttie down: the next opening starts fresh
  const face = useFace(canvas);
  const [agent, actions, history, lastChange, switching, connectionError] = useAgentStream();
  const [showHistory, setShowHistory] = useState(false);
  // The past chat open in the history (null = the list), why it could not be continued, and
  // whether it is being restored.
  const [historyChat, setHistoryChat] = useState({ id: null, error: "", resuming: false });
  const [quiet, setQuiet] = useState(false);  // the user typed: Tuttie answers in text only
  // A new answer in voice mode: shown as Tuttie speaks it ({ answer, id, text } while revealing).
  const [reveal, setReveal] = useState(null);
  // What Tuttie is doing, and the eyes following it (lib/presence.js, lib/faceDirector.js).
  const presence = usePresenceSource({ mode, agent, error, lastChange }, face);
  useFaceDirector(presence, face);
  const { state: voice, unlockAudio, muted, toggleMute } = useVoice(mode === "voice" && !quiet && !switching, onSpeech,
                                                                    presence.levels, agent.id);

  // Only a speech stream that starts after the answer arrived is the answer being read out.
  function onSpeech({ id, text, done }) {
    setReveal(r => {
      if (!r || (r.id && r.id !== id)) return r;
      if (done) return null;  // spoken to the end: show the whole answer with its formatting
      return { ...r, id, text };
    });
  }

  useEffect(() => {
    if (!agent.answer || voice !== "live") return setReveal(null);
    setReveal({ answer: agent.answer, id: null, text: "" });
    const fallback = setTimeout(() => setReveal(r => (r && !r.id ? null : r)), REVEAL_WAIT_MS);
    return () => clearTimeout(fallback);
  }, [agent.answer]);  // eslint-disable-line react-hooks/exhaustive-deps
  // The user said goodbye (Tuttie's end_conversation): once the goodbye is shown and spoken, the
  // card closes itself, as if swiped down.
  useEffect(() => {
    if (agent.closing !== "ready" || reveal || mode === "closed") return undefined;
    const timer = setTimeout(close, CLOSE_AFTER_MS);
    return () => clearTimeout(timer);
  }, [agent.closing, reveal, mode]);  // eslint-disable-line react-hooks/exhaustive-deps
  useVisibleViewport();
  const busy = Boolean(agent.turns.length || agent.request);

  function startVoice() {
    unlockAudio();
    setQuiet(false);
    if (mode === "closed") {
      openedAt.current = performance.now();
      if (closedOnce.current && !agent.approval) actions.newConversation(agent).catch(e => setError(e.message));
      closedOnce.current = false;
    }
    setMode("voice");
  }

  function close() {
    setMode("closed");
    setShowHistory(false);
    closedOnce.current = true;
  }

  // A new conversation from the dock: the current one goes into the history.
  async function newChat() {
    setShowHistory(false);
    if (agent.approval) return;  // the user must decide the waiting approval first
    try {
      await actions.newConversation(agent);
      setError("");
      presence.cue("new_chat");
    } catch (e) { setError(e.message); }
  }

  function tapWhileOpen() {
    unlockAudio();
    setQuiet(false);  // tapping Tuttie's face brings its voice back after typing
    if (mode !== "voice") return startVoice();
    presence.cue("tap");  // a tap never ends voice mode, Tuttie just reacts
  }

  // The dock's History button always shows the list, also from inside a past chat.
  function openHistory() {
    setHistoryChat({ id: null, error: "", resuming: false });
    setShowHistory(true);
  }

  // Continue a past chat: the server restores that conversation first; only then does the card
  // show it (in voice or typing). If it expired, the history says so and nothing else changes.
  async function resumeChat(entry, then) {
    if (historyChat.resuming) return;
    setHistoryChat({ id: entry.id, error: "", resuming: true });
    try {
      await actions.resume(entry);
    } catch (e) {
      return setHistoryChat({ id: entry.id, error: resumeFailure(e), resuming: false });
    }
    setHistoryChat({ id: null, error: "", resuming: false });
    setShowHistory(false);
    setError("");
    if (then === "voice") setQuiet(false);
    setMode(then);
  }

  // The keyboard types into the chat on screen: a past chat open in the history is resumed first.
  function startTyping() {
    if (performance.now() - openedAt.current <= OPEN_GUARD_MS) return;
    const viewed = showHistory && viewedChat(history, historyChat.id, agent.id);
    if (viewed) return resumeChat(viewed, "typing");
    setShowHistory(false);
    setMode("typing");
  }

  // An approval needs the user: open the card if it is closed.
  useEffect(() => {
    if (agent.approval && mode === "closed") startVoice();
  }, [agent.approval]);  // eslint-disable-line react-hooks/exhaustive-deps

  // `shown` is what the history keeps of the user's words; `text` is what Tuttie gets. A typed
  // message makes Tuttie answer quietly, in text only.
  async function send(text, firstTool = null, shown = text, typed = false) {
    if (switching || connectionError) return setError(connectionError || "Please wait for the conversation to load");
    if (typed) setQuiet(true);
    actions.say(shown);
    setShowHistory(false);
    setMode("voice");  // Tuttie is awake while it works
    setError("");
    try {
      await sendChat(text, firstTool, agent.id);
    } catch (e) {
      setError(e.message || "Tuttie is unreachable right now");
    }
  }

  // The user swiped through the cards: book the best liked deal (the lowest agreed price).
  function pick(liked) {
    const best = [...liked].sort((a, b) => (a.agreed_chf ?? a.price_chf) - (b.agreed_chf ?? b.price_chf))[0];
    actions.pick([best.node_id]);
    send(`Book ${best.name} (${best.node_id})${best.agreed_chf != null ? " at the agreed price" : ""}.`, "book",
         `Book ${best.name}`);
  }

  // While a hotel card is dragged, Tuttie looks the same way (the face director follows `lean`).
  function lean(x) {
    presence.update({ lean: x });
  }

  const classes = ["app", mode !== "closed" && "open", mode === "voice" && "voice", mode === "typing" && "typing",
                   busy && "busy"];
  return (
    <PresenceProvider value={presence}>
    <div className={classes.filter(Boolean).join(" ")}>
      <div className="head"><h1>Wallet</h1></div>
      <BankCard index={0} color="blue" />
      <BankCard index={1} color="black" />
      <AgentCard canvasRef={canvas} mode={mode} status={error || connectionError || (switching ? "Loading conversation…" : currentTask(agent))}
                 onOpen={startVoice} onClose={close} onTap={tapWhileOpen} onSend={text => send(text, null, text, true)}>
        <Activity key={agent.id} state={agent} onPick={switching ? undefined : pick} onLean={lean} reveal={reveal} />
        {showHistory && <History entries={history.filter(e => e.id !== agent.id)} open={historyChat.id}
          error={historyChat.error} resuming={historyChat.resuming} onClose={() => setShowHistory(false)}
          onOpen={id => setHistoryChat({ id, error: "", resuming: false })}
          onResume={() => resumeChat(history.find(e => e.id === historyChat.id), "voice")} />}
        <ApprovalSheet key={agent.approval?.id} approval={agent.approval} />
      </AgentCard>
      <Dock onHistory={openHistory} onNewChat={newChat} onKeyboard={startTyping}
            muted={muted || quiet} onMute={quiet ? () => setQuiet(false) : toggleMute} />
    </div>
    </PresenceProvider>
  );
}
