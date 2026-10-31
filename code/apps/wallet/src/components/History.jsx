// Past conversations on this device (lib/history.js), newest first. Tapping one shows it as it
// was; Continue chat restores the live server conversation before allowing actions.
import { useState } from "react";
import Activity from "./Activity.jsx";

const when = at => new Date(at).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });

/**
 * @param entries  archived conversations ({ id, at, title, outcome, state })
 * @param onClose  () => void
 */
export default function History({ entries, onClose, onResume }) {
  const [open, setOpen] = useState(null);
  const [error, setError] = useState("");
  const [resuming, setResuming] = useState(false);
  const entry = entries.find(e => e.id === open);
  async function resume() {
    setError("");
    setResuming(true);
    try { await onResume(entry); }
    catch (e) { setError(e.message); }
    finally { setResuming(false); }
  }
  return (
    <div className="history">
      <div className="history-bar">
        {entry ? <button type="button" disabled={resuming} onClick={() => { setOpen(null); setError(""); }}>‹ History</button> : <span>History</span>}
        {entry && <button type="button" disabled={resuming} onClick={resume}>{resuming ? "Loading…" : "Continue chat"}</button>}
        <button type="button" onClick={onClose}>Done</button>
      </div>
      {error && <div className="history-error" role="alert">{error}</div>}
      {entry ? (
        <Activity state={entry.state} readOnly />
      ) : (
        <div className="history-list" data-scroll>
          {entries.length === 0 && <div className="history-empty">No earlier conversations on this device yet.</div>}
          {entries.map(e => (
            <button type="button" className="history-item" key={e.id} onClick={() => { setOpen(e.id); setError(""); }}>
              <b>{e.title || "Conversation"}</b>
              <small>{e.outcome}</small>
              <time>{when(e.at)}</time>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
