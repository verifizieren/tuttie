// The owner view: one business on one page. Edit a few settings, review the changes, deploy.
// Edits are a draft: guests' agents keep using what is live until the owner deploys.
import { useCallback, useEffect, useMemo, useState } from "react";
import DeployDialog from "./components/DeployDialog.jsx";
import { EditorContext } from "./components/editor.jsx";
import Login from "./components/Login.jsx";
import Sections from "./components/sections.jsx";
import { useDraft } from "./hooks/useDraft.js";
import { useOverview } from "./hooks/useOverview.js";
import { forgetToken, saveToken, savedToken } from "./lib/api.js";
import { ago } from "./lib/format.js";
import { diff } from "./lib/settings.js";

/** The page for a signed-in owner, once the business has been read from its node. */
function Workspace({ token, data, error, updatedAt, refresh, accept, onSignOut }) {
  const live = data.settings;
  const draft = useDraft(data.node_id, live, data.version);
  const [errors, setErrors] = useState({});
  const [reviewing, setReviewing] = useState(false);
  const [deployedVersion, setDeployedVersion] = useState(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Problems the node reported belong to the last attempt: any new edit starts afresh.
  const set = useCallback((path, value) => { setErrors({}); draft.set(path, value); }, [draft.set]);
  const update = useCallback(change => { setErrors({}); draft.update(change); }, [draft.update]);
  const editor = useMemo(() => ({ settings: draft.settings, live, set, update, errors }),
                         [draft.settings, live, set, update, errors]);
  const changes = useMemo(() => diff(live, draft.settings), [live, draft.settings]);

  const deployed = overview => {
    draft.discard();
    accept(overview);
    setErrors({});
    setReviewing(false);
    setDeployedVersion(overview.version);
  };
  const refused = list => setErrors(Object.fromEntries(list.filter(e => e.path).map(e => [e.path, e.message])));

  useEffect(() => {
    if (deployedVersion === null) return undefined;
    const timer = setTimeout(() => setDeployedVersion(null), 6000);
    return () => clearTimeout(timer);
  }, [deployedVersion]);

  return (
    <EditorContext.Provider value={editor}>
      <main className="page">
        <header>
          <h1>{data.name}</h1>
          <p className="meta">
            {data.seals.map(seal => <i key={seal.issuer} className={`seal ${seal.tier}`} title={seal.issuer} />)}
            {data.uid && <span className="mono">{data.uid}</span>}
          </p>
          <p className="meta">
            <span className={`live ${error ? "down" : ""}`}><i /> {error ? "Offline" : "Live"} · version {data.version} · {ago(updatedAt, now)}</span>
            <button className="link" onClick={refresh}>Refresh</button>
            <button className="link" onClick={() => { draft.discard(); onSignOut(); }}>Sign out</button>
          </p>
        </header>

        {deployedVersion !== null && (
          <p className="notice" role="status">Version {deployedVersion} is live. Your agent uses it from its next request.</p>
        )}

        <Sections />

        {(draft.dirty || draft.stale) && (
          <div className="deploy-bar" role="region" aria-label="Unsaved changes">
            <span>
              {draft.stale
                ? `Version ${data.version} went live after you started. Discard your draft to continue.`
                : `${changes.length} change${changes.length === 1 ? "" : "s"}, not live yet`}
            </span>
            <div className="deploy-actions">
              <button className="secondary" onClick={() => { draft.discard(); setErrors({}); }}>Discard</button>
              {!draft.stale && <button onClick={() => setReviewing(true)}>Review</button>}
            </div>
          </div>
        )}

        {reviewing && (
          <DeployDialog token={token} baseVersion={draft.baseVersion} settings={draft.settings} changes={changes}
                        onClose={() => setReviewing(false)} onDeployed={deployed} onRefused={refused} />
        )}
      </main>
    </EditorContext.Provider>
  );
}

/** Reads the business and hands it to the workspace; a refused token goes back to the login. */
function Dashboard({ token, onSignOut }) {
  const overview = useOverview(token);
  const { data, error } = overview;

  // A refused token goes back to the login with the node's reason; nothing else signs out.
  useEffect(() => {
    if (error && (error.status === 401 || error.status === 503)) onSignOut(error.message);
  }, [error, onSignOut]);

  if (!data) return <main className="center muted">{error ? error.message : "Loading…"}</main>;
  return <Workspace key={data.node_id} token={token} {...overview} onSignOut={onSignOut} />;
}

export default function App() {
  const [token, setToken] = useState(savedToken());
  const [problem, setProblem] = useState(null);

  const signOut = useCallback(reason => {
    forgetToken();
    setToken("");
    setProblem(typeof reason === "string" ? reason : null);
  }, []);
  const signIn = value => {
    saveToken(value);
    setProblem(null);
    setToken(value);
  };

  return token ? <Dashboard token={token} onSignOut={signOut} /> : <Login onSubmit={signIn} problem={problem} />;
}
