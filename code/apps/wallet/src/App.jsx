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

// Taps on the controls right after opening are ignored, so the tap that opens the card can
// never land on the keyboard icon.
const OPEN_GUARD_MS = 700;
const REVEAL_WAIT_MS = 3000;  // no speech for a new answer by then: show it in full at once

export default function App() {
  const [mode, setMode] = useState("closed");
  const [error, setError] = useState("");  // the only text under the eyes: Tuttie cannot be reached
  const canvas = useRef(null);
  const openedAt = useRef(0);
  const closedOnce = useRef(false);  // the user swiped Tuttie down: the next opening starts fresh
  const face = useFace(canvas);
  const [agent, actions, history, lastChange] = useAgentStream();
  const [showHistory, setShowHistory] = useState(false);
  const [quiet, setQuiet] = useState(false);  // the user typed: Tuttie answers in text only
  // A new answer in voice mode: shown as Tuttie speaks it ({ answer, id, text } while revealing).
  const [reveal, setReveal] = useState(null);
  // What Tuttie is doing, and the eyes following it (lib/presence.js, lib/faceDirector.js).
  const presence = usePresenceSource({ mode, agent, error, lastChange }, face);
  useFaceDirector(presence, face);
  const { state: voice, unlockAudio, muted, toggleMute } = useVoice(mode === "voice" && !quiet, onSpeech,
                                                                    presence.levels);

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
  useVisibleViewport();
  const busy = Boolean(agent.turns.length || agent.request);

  function startVoice() {
    unlockAudio();
    setQuiet(false);
    if (mode === "closed") {
      openedAt.current = performance.now();
      if (closedOnce.current && !agent.approval) actions.newConversation(agent);
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
  function newChat() {
    setShowHistory(false);
    if (agent.approval) return;  // the user must decide the waiting approval first
    actions.newConversation(agent);
    presence.cue("new_chat");
  }

  function tapWhileOpen() {
    unlockAudio();
    setQuiet(false);  // tapping Tuttie's face brings its voice back after typing
    if (mode !== "voice") return startVoice();
    presence.cue("tap");  // a tap never ends voice mode, Tuttie just reacts
  }

  function startTyping() {
    if (performance.now() - openedAt.current > OPEN_GUARD_MS) setMode("typing");
  }

  // An approval needs the user: open the card if it is closed.
  useEffect(() => {
    if (agent.approval && mode === "closed") startVoice();
  }, [agent.approval]);  // eslint-disable-line react-hooks/exhaustive-deps

  // `shown` is what the history keeps of the user's words; `text` is what Tuttie gets. A typed
  // message makes Tuttie answer quietly, in text only.
  async function send(text, firstTool = null, shown = text, typed = false) {
    if (typed) setQuiet(true);
    actions.say(shown);
    setShowHistory(false);
    setMode("voice");  // Tuttie is awake while it works
    setError("");
    try {
      await sendChat(text, firstTool);
    } catch {
      setError("Tuttie is unreachable right now");
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
      <AgentCard canvasRef={canvas} mode={mode} status={error || currentTask(agent)}
                 onOpen={startVoice} onClose={close} onTap={tapWhileOpen} onSend={text => send(text, null, text, true)}>
        <Activity state={agent} onPick={pick} onLean={lean} reveal={reveal} />
        {showHistory && <History entries={history} onClose={() => setShowHistory(false)} />}
        <ApprovalSheet key={agent.approval?.id} approval={agent.approval} />
      </AgentCard>
      <Dock onHistory={() => setShowHistory(true)} onNewChat={newChat} onKeyboard={startTyping}
            muted={muted || quiet} onMute={quiet ? () => setQuiet(false) : toggleMute} />
    </div>
    </PresenceProvider>
  );
}
