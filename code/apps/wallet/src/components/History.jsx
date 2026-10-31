// Past conversations on this device (lib/history.js), newest first. Tapping one shows it as it
// was; Continue chat (or the dock's keyboard) restores the live server conversation before
// allowing actions. Which chat is open, and why it could not be continued, is kept by App, so the
// dock's History button always leads back to this list.
import Activity from "./Activity.jsx";

const when = at => new Date(at).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });

/**
 * @param entries   archived conversations ({ id, at, title, outcome, state })
 * @param open      the id of the chat shown, or null for the list
 * @param onOpen    (id | null) => void: show a chat, or back to the list
 * @param error     why the open chat could not be continued ("" if nothing failed)
 * @param resuming  the open chat is being restored on the server
 * @param onResume  () => void: continue the open chat
 * @param onClose   () => void
 */
export default function History({ entries, open, onOpen, error, resuming, onResume, onClose }) {
  const entry = entries.find(e => e.id === open);
  return (
    <div className="history">
      <div className="history-bar">
        {entry ? <button type="button" disabled={resuming} onClick={() => onOpen(null)}>‹ History</button> : <span>History</span>}
        {entry && <button type="button" disabled={resuming} onClick={onResume}>{resuming ? "Loading…" : "Continue chat"}</button>}
        <button type="button" onClick={onClose}>Done</button>
      </div>
      {entry && error && <div className="history-error" role="alert">{error}</div>}
      {entry ? (
        <Activity state={entry.state} readOnly />
      ) : (
        <div className="history-list" data-scroll>
          {entries.length === 0 && <div className="history-empty">No earlier conversations on this device yet.</div>}
          {entries.map(e => (
            <button type="button" className="history-item" key={e.id} onClick={() => onOpen(e.id)}>
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
