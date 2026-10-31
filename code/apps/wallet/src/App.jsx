// The wallet screen: two generic bank cards and the Tuttie card, which is the agent's face.
//
// The agent has three modes:
//   closed  card in the stack, eyes closed (asleep)
//   voice   card open, eyes open; this is the main interface and stays on until the user
//           swipes the card down or switches to typing; taps never send Tuttie away
//   typing  card open with a text field; the eyes close while the user types
//
// UI only for now: voice and text are not connected to the agent backend yet.
import { useEffect, useRef, useState } from "react";
import AgentCard from "./components/AgentCard.jsx";
import BankCard from "./components/BankCard.jsx";
import useFace from "./hooks/useFace.js";
import useVisibleViewport from "./hooks/useVisibleViewport.js";

const STATUS = {
  closed: "Tap Tuttie to talk",
  voice: "Listening…",
  typing: "Tap Tuttie to talk instead",
};
// Taps on the controls right after opening are ignored, so the tap that opens the card can
// never land on the keyboard icon.
const OPEN_GUARD_MS = 700;

export default function App() {
  const [mode, setMode] = useState("closed");
  const [said, setSaid] = useState("");
  const [status, setStatus] = useState(STATUS.closed);
  const canvas = useRef(null);
  const openedAt = useRef(0);
  const face = useFace(canvas);
  useVisibleViewport();

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

  function send(text) {
    setSaid(`“${text}”`);
    setStatus("Not connected to the agent web yet");
  }

  const classes = ["app", mode !== "closed" && "open", mode === "voice" && "voice", mode === "typing" && "typing"];
  return (
    <div className={classes.filter(Boolean).join(" ")}>
      <div className="head"><h1>Wallet</h1></div>
      <BankCard index={0} color="blue" />
      <BankCard index={1} color="black" />
      <AgentCard canvasRef={canvas} mode={mode} said={said} status={status}
                 onOpen={startVoice} onClose={close} onTap={tapWhileOpen}
                 onKeyboard={startTyping} onSend={send} />
    </div>
  );
}
