// The controls at the bottom of the open Tuttie card: what Tuttie is doing right now (or a
// problem), and while typing the text field. Listening and thinking show in Tuttie's eyes,
// not here; typing is chosen with the keyboard in the dock.
import { useEffect, useRef, useState } from "react";

/**
 * @param mode    "closed" | "voice" | "typing"
 * @param status  the task Tuttie is doing now, a problem (e.g. it cannot be reached), or ""
 * @param onSend  (text) => void
 */
export default function AgentControls({ mode, status, onSend }) {
  const input = useRef(null);
  const [text, setText] = useState("");

  // The keyboard opens only when the user chose to type, never on its own.
  useEffect(() => {
    if (mode === "typing") input.current?.focus({ preventScroll: true });
    else input.current?.blur();
  }, [mode]);

  function submit(e) {
    e.preventDefault();
    if (!text.trim()) return;
    onSend(text.trim());
    setText("");
  }

  return (
    <div className="controls">
      {status && <div className="status">{status}</div>}
      {mode === "typing" && (
        <form className="composer" onSubmit={submit} autoComplete="off">
          <input ref={input} value={text} onChange={e => setText(e.target.value)}
                 placeholder="Message Tuttie…" enterKeyHint="send" />
          <button type="submit">Send</button>
        </form>
      )}
    </div>
  );
}
