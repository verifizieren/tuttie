// The controls at the bottom of the open Tuttie card: what Tuttie is doing right now (or a
// problem), and while typing the text field. Listening and thinking show in Tuttie's eyes,
// not here; typing is chosen with the keyboard in the dock.
import { useEffect, useRef, useState } from "react";

/**
 * @param mode    "closed" | "voice" | "typing"
 * @param status  the task Tuttie is doing now, a problem (e.g. it cannot be reached), or ""
 * @param onSend  (text) => Promise<boolean>: false if the text did not reach Tuttie
 */
export default function AgentControls({ mode, status, onSend }) {
  const input = useRef(null);
  const [text, setText] = useState("");

  // The keyboard opens only when the user chose to type, never on its own.
  useEffect(() => {
    if (mode === "typing") input.current?.focus({ preventScroll: true });
    else input.current?.blur();
  }, [mode]);

  // A message that did not reach Tuttie comes back into the field (unless the user already
  // typed something new), so it is never lost.
  async function submit(e) {
    e.preventDefault();
    const sent = text.trim();
    if (!sent) return;
    setText("");
    if (await onSend(sent) === false) setText(current => current || sent);
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
