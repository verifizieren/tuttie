// Past conversations on this device (lib/history.js), newest first. Tapping one shows it as it
// was, read-only. Opened with a swipe right on Tuttie's card, closed with "Done" or a swipe left.
import { useState } from "react";
import Activity from "./Activity.jsx";

const when = at => new Date(at).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });

/**
 * @param entries  archived conversations ({ id, at, title, outcome, state })
 * @param onClose  () => void
 */
export default function History({ entries, onClose }) {
  const [open, setOpen] = useState(null);
  const entry = entries.find(e => e.id === open);
  return (
    <div className="history">
      <div className="history-bar">
        {entry ? <button type="button" onClick={() => setOpen(null)}>‹ History</button> : <span>History</span>}
        <button type="button" onClick={onClose}>Done</button>
      </div>
      {entry ? (
        <Activity state={entry.state} readOnly />
      ) : (
        <div className="history-list" data-scroll>
          {entries.length === 0 && <div className="history-empty">No earlier conversations on this device yet.</div>}
          {entries.map(e => (
            <button type="button" className="history-item" key={e.id} onClick={() => setOpen(e.id)}>
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
