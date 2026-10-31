// The controls at the bottom of the open Tuttie card: a status line and the text fallback. Voice is the main interface; typing is a deliberate choice behind a small,
// dim keyboard icon, and the text field only exists while typing.
import { useEffect, useRef, useState } from "react";

function KeyboardIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      <rect x="2.5" y="6" width="19" height="12" rx="2.5" />
      <path d="M6 10h.01M9.5 10h.01M13 10h.01M16.5 10h.01M7.5 14h9" />
    </svg>
  );
}

/**
 * @param mode       "closed" | "voice" | "typing"
 * @param status     the status line under it
 * @param onKeyboard switch to typing
 * @param onSend     (text) => void
 */
export default function AgentControls({ mode, status, onKeyboard, onSend }) {
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
      <div className="status">{status}</div>
      {mode === "typing" ? (
        <form className="composer" onSubmit={submit} autoComplete="off">
          <input ref={input} value={text} onChange={e => setText(e.target.value)}
                 placeholder="Message Tuttie…" enterKeyHint="send" />
          <button type="submit">Send</button>
        </form>
      ) : (
        <button className="kbd" type="button" aria-label="Type instead" onClick={onKeyboard}>
          <KeyboardIcon />
        </button>
      )}
    </div>
  );
}
