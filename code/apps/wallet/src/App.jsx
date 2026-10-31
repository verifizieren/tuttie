// The wallet screen: two generic bank cards and the Tuttie card, which is the agent's face.
//
// The agent has three modes:
//   closed  card in the stack, eyes closed (asleep)
//   voice   card open, eyes open; this is the main interface and stays on until the user
//           swipes the card down or switches to typing; taps never send Tuttie away
//   typing  card open with a text field; the eyes close while the user types
//
// Text goes to Tuttie (POST /chat); what Tuttie then does on the agent web arrives on the
// event stream and is shown under its eyes (Activity), including the approval sheet. Voice
// recognition is its own work area (code/voice) and not connected yet.
import { useEffect, useRef, useState } from "react";
import Activity from "./components/Activity.jsx";
import AgentCard from "./components/AgentCard.jsx";
import ApprovalSheet from "./components/ApprovalSheet.jsx";
import BankCard from "./components/BankCard.jsx";
import useAgentStream from "./hooks/useAgentStream.js";
import useFace from "./hooks/useFace.js";
import useVisibleViewport from "./hooks/useVisibleViewport.js";
import { sendChat } from "./lib/api.js";
import { BUSY, EXPRESSION, MOOD, THINKING, statusLine } from "./lib/activity.js";

const STATUS = {
  closed: "Tap Tuttie to talk",
  voice: "Listening…",
  typing: "Tap Tuttie to talk instead",
};
// Taps on the controls right after opening are ignored, so the tap that opens the card can
// never land on the keyboard icon.
const THINKING_MS = 1600;  // how long each thinking look lasts
const OPEN_GUARD_MS = 700;

export default function App() {
  const [mode, setMode] = useState("closed");
  const [said, setSaid] = useState("");
  const [status, setStatus] = useState(STATUS.closed);
  const canvas = useRef(null);
  const openedAt = useRef(0);
  const face = useFace(canvas);
  const [agent, startRun] = useAgentStream();
  useVisibleViewport();
  const busy = Boolean(agent.request || agent.answer || agent.phase !== "idle");

  // The face follows the mode: awake and briefly happy in voice mode, asleep otherwise.
  useEffect(() => {
    setStatus(STATUS[mode]);
    if (mode !== "voice") {
      face.current?.sleep();
      return undefined;
    }
    face.current?.wake("happiness");
    const calm = setTimeout(() => face.current?.set("neutral", 700), 1300);
    return () => clearTimeout(calm);
  }, [mode, face]);

  function startVoice() {
    if (mode === "closed") openedAt.current = performance.now();
    setMode("voice");
  }

  function close() {
    setMode("closed");
    setSaid("");
  }

  function tapWhileOpen() {
    if (mode !== "voice") return startVoice();
    face.current?.set("excitement", 250);  // a tap never ends voice mode, Tuttie just reacts
    setTimeout(() => face.current?.set("neutral", 500), 600);
  }

  function startTyping() {
    if (performance.now() - openedAt.current > OPEN_GUARD_MS) setMode("typing");
  }

  // While Tuttie works, its face follows what is happening on the agent web.
  // While it is busy, it moves through a few thinking looks instead of holding one.
  useEffect(() => {
    if (mode !== "voice" || !EXPRESSION[agent.phase]) return;
    // A finished answer shows how it feels: glad about a deal, sorry about bad news.
    face.current?.set(agent.phase === "done" ? MOOD[agent.mood] || "happiness" : EXPRESSION[agent.phase], 500);
    if (!BUSY.has(agent.phase)) return;
    let i = 0;
    const timer = setInterval(() => {
      const { name, look } = THINKING[i++ % THINKING.length];
      face.current?.set(name, 600);
      face.current?.lookAt(look[0], look[1], 600);
    }, THINKING_MS);
    return () => clearInterval(timer);
  }, [agent.phase, agent.mood, mode, face]);

  // An approval needs the user: open the card if it is closed.
  useEffect(() => {
    if (agent.approval && mode === "closed") startVoice();
  }, [agent.approval]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function send(text) {
    setSaid(`“${text}”`);
    startRun();
    setMode("voice");  // Tuttie is awake while it works
    try {
      await sendChat(text);
    } catch {
      setStatus("Tuttie is unreachable right now");
    }
  }

  const classes = ["app", mode !== "closed" && "open", mode === "voice" && "voice", mode === "typing" && "typing",
                   busy && "busy"];
  return (
    <div className={classes.filter(Boolean).join(" ")}>
      <div className="head"><h1>Wallet</h1></div>
      <BankCard index={0} color="blue" />
      <BankCard index={1} color="black" />
      <AgentCard canvasRef={canvas} mode={mode} said={busy ? "" : said} status={statusLine(agent) || status}
                 onOpen={startVoice} onClose={close} onTap={tapWhileOpen}
                 onKeyboard={startTyping} onSend={send}>
        <Activity state={agent} />
        <ApprovalSheet key={agent.approval?.id} approval={agent.approval} />
      </AgentCard>
    </div>
  );
}
