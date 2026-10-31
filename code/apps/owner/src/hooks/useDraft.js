// The owner's unsaved changes: a draft of the settings that lives in this browser until it is
// deployed or discarded. The page shows the draft when there is one, else what is live.
//
// A draft remembers the live version it started from. If someone deploys meanwhile the draft
// is `stale`: it can still be read, but deploying it would overwrite the newer version, so the
// owner must discard it first (the node refuses such a deploy too).
import { useCallback, useEffect, useState } from "react";
import { sameSettings, setIn } from "../lib/settings.js";

const keyFor = nodeId => `tuttie_owner_draft:${nodeId}`;

function stored(nodeId) {
  try {
    return JSON.parse(localStorage.getItem(keyFor(nodeId)));
  } catch {
    return null;
  }
}

export function useDraft(nodeId, live, version) {
  const [draft, setDraft] = useState(() => stored(nodeId));

  useEffect(() => {
    if (draft) localStorage.setItem(keyFor(nodeId), JSON.stringify(draft));
    else localStorage.removeItem(keyFor(nodeId));
  }, [draft, nodeId]);

  /** Change the settings with `change(settings) -> settings`, starting a draft if there is none.
   *  A draft that ends up equal to what is live is dropped. */
  const update = useCallback(change => {
    setDraft(previous => {
      const base = previous ? previous.settings : live;
      const next = change(base);
      const started = previous ? previous.base_version : version;
      return sameSettings(next, live) && started === version ? null : { base_version: started, settings: next };
    });
  }, [live, version]);

  const set = useCallback((path, value) => update(settings => setIn(settings, path, value)), [update]);
  const discard = useCallback(() => setDraft(null), []);
  const restore = useCallback(settings => update(() => settings), [update]);

  const settings = draft ? draft.settings : live;
  return {
    settings,
    dirty: Boolean(draft) && !sameSettings(draft.settings, live),
    stale: Boolean(draft) && draft.base_version !== version,
    baseVersion: draft ? draft.base_version : version,
    update, set, discard, restore,
  };
}
