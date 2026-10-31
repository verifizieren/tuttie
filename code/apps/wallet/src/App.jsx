// The wallet screen: two generic bank cards and the Tuttie card, which is the agent's face.
//
// The agent has three modes:
//   closed  card in the stack, eyes closed (asleep)
//   voice   card open, eyes open; this is the main interface and stays on until the user
//           swipes the card down or switches to typing; taps never send Tuttie away
//   typing  card open with a text field; the eyes close while the user types
//
// Text goes to Tuttie (POST /chat); in voice mode the user simply talks (hooks/useVoice.js,
// code/voice) and Tuttie answers aloud. What Tuttie does on the agent web arrives on the event
// stream and is shown under its eyes (Activity), including the approval sheet.
//
// There is one conversation at a time: once the user swipes Tuttie down, the next opening
// starts a fresh one (unless an approval still waits for the user). The dock under the open
// card shows earlier conversations (kept on this device), starts a new one, or switches to typing.
import { useEffect, useRef, useState } from "react";
import Activity from "./components/Activity.jsx";
import AgentCard from "./components/AgentCard.jsx";
import ApprovalSheet from "./components/ApprovalSheet.jsx";
import BankCard from "./components/BankCard.jsx";
import Dock from "./components/Dock.jsx";
import History from "./components/History.jsx";
import useAgentStream from "./hooks/useAgentStream.js";
import useFace from "./hooks/useFace.js";
import useVisibleViewport from "./hooks/useVisibleViewport.js";
import useVoice from "./hooks/useVoice.js";
import { sendChat } from "./lib/api.js";
import { BUSY, EXPRESSION, LISTENING, MOOD, THINKING, WATCHING, currentTask } from "./lib/activity.js";

// Taps on the controls right after opening are ignored, so the tap that opens the card can
// never land on the keyboard icon.
const OPEN_GUARD_MS = 700;
const LOOK_MS = 1600;      // how long each look of a loop (thinking, listening, watching) lasts
const SETTLE_MS = { idle: 1300, done: 3500, declined: 3500 };  // the first face holds this long before listening

export default function App() {
  const [mode, setMode] = useState("closed");
  const [error, setError] = useState("");  // the only text under the eyes: Tuttie cannot be reached
  const leaning = useRef(false);           // a hotel card is being dragged: the eyes follow it
  const canvas = useRef(null);
  const openedAt = useRef(0);
  const closedOnce = useRef(false);  // the user swiped Tuttie down: the next opening starts fresh
  const face = useFace(canvas);
  const [agent, actions, history] = useAgentStream();
  const [showHistory, setShowHistory] = useState(false);
  const [, unlockAudio] = useVoice(mode === "voice", face);
  useVisibleViewport();
  const busy = Boolean(agent.turns.length || agent.request);

  // The face follows the mode: awake in voice mode, asleep otherwise.
  useEffect(() => {
    if (mode !== "voice") {
      face.current?.sleep();
      return;
    }
    face.current?.wake("happiness");
  }, [mode, face]);

  function startVoice() {
    unlockAudio();
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
    face.current?.set("happiness", 300);
    setTimeout(() => face.current?.set("neutral", 600), 700);
  }

  function tapWhileOpen() {
    unlockAudio();
    if (mode !== "voice") return startVoice();
    face.current?.set("excitement", 250);  // a tap never ends voice mode, Tuttie just reacts
    setTimeout(() => face.current?.set("neutral", 500), 600);
  }

  function startTyping() {
    if (performance.now() - openedAt.current > OPEN_GUARD_MS) setMode("typing");
  }

  // While Tuttie works, its face follows what is happening on the agent web.
  // It never holds one face: while busy it moves through thinking looks, while the user swipes
  // the cards it looks down at them, and otherwise it listens (open eyes, small glances, a nod).
  // A finished answer first shows how it feels: glad about a deal, sorry about bad news.
  useEffect(() => {
    if (mode !== "voice") return;
    const phase = agent.phase;
    const first = phase === "done" ? MOOD[agent.mood] || "happiness" : EXPRESSION[phase];
    if (first) face.current?.set(first, 500);
    const looks = BUSY.has(phase) ? THINKING : phase === "picking" ? WATCHING : phase === "approval" ? null : LISTENING;
    if (!looks) return;
    let i = 0, timer;
    const start = setTimeout(() => {
      const step = () => {
        if (leaning.current) return;  // the eyes are following a dragged card
        const { name, look } = looks[i++ % looks.length];
        face.current?.set(name, 600);
        face.current?.lookAt(look[0], look[1], 600);
      };
      step();
      timer = setInterval(step, LOOK_MS);
    }, BUSY.has(phase) ? LOOK_MS : SETTLE_MS[phase] ?? 0);
    return () => { clearTimeout(start); clearInterval(timer); };
  }, [agent.phase, agent.mood, mode, face]);

  // An approval needs the user: open the card if it is closed.
  useEffect(() => {
    if (agent.approval && mode === "closed") startVoice();
  }, [agent.approval]);  // eslint-disable-line react-hooks/exhaustive-deps

  // `shown` is what the history keeps of the user's words; `text` is what Tuttie gets.
  async function send(text, firstTool = null, shown = text) {
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

  // While a hotel card is dragged, Tuttie looks the same way.
  function lean(x) {
    leaning.current = x !== 0;
    face.current?.lookAt(x, 0, 120);
  }

  const classes = ["app", mode !== "closed" && "open", mode === "voice" && "voice", mode === "typing" && "typing",
                   busy && "busy"];
  return (
    <div className={classes.filter(Boolean).join(" ")}>
      <div className="head"><h1>Wallet</h1></div>
      <BankCard index={0} color="blue" />
      <BankCard index={1} color="black" />
      <AgentCard canvasRef={canvas} mode={mode} status={error || currentTask(agent)}
                 onOpen={startVoice} onClose={close} onTap={tapWhileOpen} onSend={send}>
        <Activity state={agent} onPick={pick} onLean={lean} />
        {showHistory && <History entries={history} onClose={() => setShowHistory(false)} />}
        <ApprovalSheet key={agent.approval?.id} approval={agent.approval} />
      </AgentCard>
      <Dock onHistory={() => setShowHistory(true)} onNewChat={newChat} onKeyboard={startTyping} />
    </div>
  );
}
