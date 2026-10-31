// The owner view: one business. A sidebar of sections, the live state in the header, forms that
// edit a draft and a bar to review and deploy it. Nothing reaches guests until it is deployed.
import { useCallback, useEffect, useMemo, useState } from "react";
import DeployDialog from "./components/DeployDialog.jsx";
import { EditorContext } from "./components/editor.jsx";
import Login from "./components/Login.jsx";
import { SECTIONS } from "./components/sections.jsx";
import Versions, { formatTime } from "./components/Versions.jsx";
import { useDraft } from "./hooks/useDraft.js";
import { useOverview } from "./hooks/useOverview.js";
import { forgetToken, saveToken, savedToken } from "./lib/api.js";
import { ago } from "./lib/format.js";
import { diff } from "./lib/settings.js";

const HISTORY = { id: "versions", label: "Versions" };

/** The page for a signed-in owner, once the business has been read from its node. */
function Workspace({ token, data, error, updatedAt, refresh, accept, onSignOut }) {
  const live = data.settings;
  const draft = useDraft(data.node_id, live, data.version);
  const [sectionId, setSectionId] = useState(SECTIONS[0].id);
  const [errors, setErrors] = useState({});
  const [reviewing, setReviewing] = useState(false);
  const [notice, setNotice] = useState(null);
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
    setNotice(`Version ${overview.version} is live. Your agent uses the new settings from its next request.`);
  };
  const restored = version => {
    draft.restore(version.settings);
    setSectionId(SECTIONS[0].id);
    setNotice(`Version ${version.version} is loaded as a draft. Review it and deploy to go back to it.`);
  };
  const refused = list => setErrors(Object.fromEntries(list.filter(e => e.path).map(e => [e.path, e.message])));

  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => setNotice(null), 8000);
    return () => clearTimeout(timer);
  }, [notice]);

  const showingHistory = sectionId === HISTORY.id;
  const section = showingHistory ? HISTORY : SECTIONS.find(s => s.id === sectionId);
  const Section = showingHistory ? null : section.component;
  const offline = Boolean(error);

  return (
    <EditorContext.Provider value={editor}>
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">Tuttie <span>for business</span></div>
          <nav>
            {[...SECTIONS, HISTORY].map(s => (
              <button key={s.id} className={`nav ${s.id === sectionId ? "active" : ""}`} onClick={() => setSectionId(s.id)}>
                {s.label}
                {s.private && <span className="lock" title="Private">private</span>}
              </button>
            ))}
          </nav>
          <button className="link" onClick={() => { draft.discard(); onSignOut(); }}>Sign out</button>
        </aside>

        <main className="main">
          <header className="topbar">
            <div>
              <h1>{data.name}</h1>
              <p className="muted">{section.label}</p>
            </div>
            <div className="topbar-side">
              <span className={`live ${offline ? "down" : ""}`}>
                <i /> {offline ? "Offline, showing the last state" : "Live"} · {ago(updatedAt, now)}
              </span>
              <button className="secondary" onClick={refresh}>Refresh</button>
            </div>
          </header>

          {notice && <div className="banner success" role="status">{notice}</div>}
          <div className={`banner ${draft.dirty ? "draft" : ""}`}>
            {draft.dirty
              ? `You are editing a draft. Guests' agents keep using version ${data.version} until you deploy.`
              : `Live: version ${data.version}${data.deployed_at ? `, deployed ${formatTime(data.deployed_at)}` : ", the original configuration"}.${showingHistory ? "" : " Change anything below, then review and deploy."}`}
          </div>

          {showingHistory
            ? <Versions token={token} liveVersion={data.version} onRestore={restored} />
            : <Section data={data} />}

          {(draft.dirty || draft.stale) && (
            <div className="deploy-bar" role="region" aria-label="Unsaved changes">
              <span>
                {draft.stale
                  ? `Version ${data.version} was deployed after you started this draft. Discard the draft to continue from it.`
                  : `${changes.length} change${changes.length === 1 ? "" : "s"} not deployed yet`}
              </span>
              <div className="deploy-actions">
                <button className="secondary" onClick={() => { draft.discard(); setErrors({}); }}>Discard draft</button>
                {!draft.stale && <button onClick={() => setReviewing(true)}>Review and deploy</button>}
              </div>
            </div>
          )}
        </main>

        {reviewing && (
          <DeployDialog token={token} baseVersion={draft.baseVersion} settings={draft.settings} changes={changes}
                        onClose={() => setReviewing(false)} onDeployed={deployed} onRefused={refused} />
        )}
      </div>
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

  if (!data) return <main className="center muted">{error ? error.message : "Loading your business…"}</main>;
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
