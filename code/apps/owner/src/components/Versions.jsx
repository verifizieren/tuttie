// The history of deployed versions. Version 0 is the configuration the business started with.
// "Restore as draft" puts an old version into the editor; going back is a new deploy.
import { useEffect, useState } from "react";
import { fetchVersions } from "../lib/api.js";
import { diff } from "../lib/settings.js";
import Changes from "./Changes.jsx";
import { Card } from "./ui.jsx";

export function formatTime(iso) {
  return iso ? new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : null;
}

export default function Versions({ token, liveVersion, onRestore }) {
  const [versions, setVersions] = useState(null);
  const [failed, setFailed] = useState(null);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchVersions(token, controller.signal).then(setVersions, failure => {
      if (failure.name !== "AbortError") setFailed(failure.message);
    });
    return () => controller.abort();
  }, [token, liveVersion]);

  if (failed) return <Card><p className="problem-text">{failed}</p></Card>;
  if (!versions) return <Card><p className="muted">Loading the history…</p></Card>;

  return (
    <Card title="Versions" note="Every deploy is kept. To go back, restore an old version as a draft and deploy it again.">
      <ul className="versions">
        {versions.map((version, index) => {
          const before = versions[index + 1];
          const live = version.version === liveVersion;
          return (
            <li key={version.version}>
              <div className="version-head">
                <strong>Version {version.version}</strong>
                {live && <span className="status on">Live</span>}
                <span className="muted">{formatTime(version.deployed_at) || "from the start"}</span>
                <span className="grow">{version.note && version.version > 0 ? `“${version.note}”` : version.version === 0 ? version.note : ""}</span>
                {before && (
                  <button type="button" className="secondary" onClick={() => setOpen(open === version.version ? null : version.version)}>
                    {open === version.version ? "Hide changes" : "Show changes"}
                  </button>
                )}
                {!live && <button type="button" className="secondary" onClick={() => onRestore(version)}>Restore as draft</button>}
              </div>
              {before && open === version.version && <Changes changes={diff(before.settings, version.settings)} />}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
