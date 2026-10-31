// Review what will change and deploy it. The node checks the settings again (it never trusts
// the page): if it refuses, its problems are listed here and marked on the fields.
import { useState } from "react";
import { deploySettings } from "../lib/api.js";
import { describePath } from "../lib/settings.js";
import Changes from "./Changes.jsx";

export default function DeployDialog({ token, baseVersion, settings, changes, onClose, onDeployed, onRefused }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState(null); // {message, errors}

  const deploy = async () => {
    setBusy(true);
    setProblem(null);
    try {
      onDeployed(await deploySettings(token, baseVersion, settings, note.trim()));
    } catch (failure) {
      setBusy(false);
      if (failure.errors?.length) onRefused(failure.errors);
      setProblem({ message: failure.message, errors: failure.errors || [] });
    }
  };

  return (
    <div className="backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label="Review and deploy">
        <h2>Review and deploy</h2>
        <p className="muted">
          These changes go live for every guest's agent as soon as you deploy. Your agent will use them from its next request.
        </p>
        <Changes changes={changes} />

        <label htmlFor="note" className="muted small">Note for the version history (optional)</label>
        <input id="note" className="input" maxLength={200} value={note} placeholder="e.g. Autumn prices"
               onChange={event => setNote(event.target.value)} />

        {problem && (
          <div className="refused" role="alert">
            <strong>{problem.errors.length ? "The node did not accept these settings:" : problem.message}</strong>
            {problem.errors.length > 0 && (
              <ul>
                {problem.errors.map((error, index) => (
                  <li key={index}>{error.path && <b>{describePath(error.path, settings)}: </b>}{error.message}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="dialog-actions">
          <button type="button" className="secondary" onClick={onClose} disabled={busy}>
            {problem?.errors.length ? "Back to editing" : "Cancel"}
          </button>
          <button type="button" onClick={deploy} disabled={busy || problem?.errors.length > 0}>
            {busy ? "Deploying…" : "Deploy to your agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
