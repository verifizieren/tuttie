"""Deployed versions of a business's settings, kept on disk next to the node.

Version 0 is the committed node config (`data/nodes/<node>.json`), which is never rewritten.
Every deploy by the owner becomes the next version in `data/deployments/<node_id>.json`
(git-ignored runtime state): its settings, the time and an optional note. The node applies the
latest version over its config when it starts and again right after a deploy, so the agent
works with the newly deployed settings from the next request on. Rolling back means
deploying an older version's settings again as a new version, so history is never lost.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from node.settings import Settings, canonical, snapshot, validate

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL_NOTE = "Original configuration"
log = logging.getLogger(__name__)


def default_dir() -> Path:
    """Where versions are kept: `OWNER_DATA_DIR` if set (read per call, so tests can redirect it)."""
    return Path(os.environ.get("OWNER_DATA_DIR") or ROOT / "data" / "deployments")


class DeploymentStore:
    """The version history of one node's settings; safe to use from several request threads."""

    def __init__(self, node_id: str, base_config: dict, directory: Path | None = None):
        self.path = (directory or default_dir()) / f"{node_id}.json"
        self.lock = threading.Lock()
        self.original = {"version": 0, "deployed_at": None, "note": ORIGINAL_NOTE,
                         "settings": canonical(snapshot(base_config))}
        self.skipped: list[dict] = []  # stored versions that no longer pass the checks
        self.versions: list[dict] = self.load()

    def load(self) -> list[dict]:
        """The stored versions that pass today's checks, oldest first. A version a newer,
        stricter check rejects is skipped (logged, kept on disk) and the newest valid one, or
        the config, is live: one bad record must not stop the node and with it every service.
        A file that is not readable JSON still stops the node (it is not overwritten)."""
        if not self.path.exists():
            return []
        valid = []
        for record in json.loads(self.path.read_text())["versions"]:
            _, errors = validate(record.get("settings"))
            if errors:
                log.error("%s: skipping version %s, it is invalid now: %s", self.path, record.get("version"), errors[0])
                self.skipped.append(record)
            else:
                valid.append(record)
        return valid

    @property
    def current(self) -> dict:
        """The live version's record."""
        return self.versions[-1] if self.versions else self.original

    def history(self) -> list[dict]:
        """All versions, newest first, version 0 last."""
        return [*reversed(self.versions), self.original]

    def deploy(self, settings: Settings, note: str | None) -> dict:
        """Store `settings` as the next version and return its record (write first, then
        remember: a failed write leaves the live version unchanged). Call with the lock held."""
        newest = max([self.current["version"], *(r.get("version", 0) for r in self.skipped)])
        record = {"version": newest + 1,
                  "deployed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "note": (note or "").strip() or None,
                  "settings": canonical(settings)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        stored = sorted([*self.versions, *self.skipped], key=lambda r: r.get("version", 0)) + [record]
        temporary.write_text(json.dumps({"versions": stored}, indent=2, ensure_ascii=False))
        temporary.replace(self.path)  # atomic: a crash never leaves half a history
        self.versions.append(record)
        return record
