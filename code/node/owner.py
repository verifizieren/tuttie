"""Owner endpoints of a node: what the owner view (apps/owner) reads and deploys.

    GET  /owner/overview   the business as it is live right now: facts (including the private
                           negotiation limits), the agent's persona and tools, wake-ups, seals,
                           the editable `settings` and the live `version`
    GET  /owner/versions   every deployed version, newest first, with its settings
    POST /owner/deploy     {base_version, settings, note}: check the settings, store them as the
                           next version and make the agent use them right away

The endpoints hold private facts (`PRIVATE_FACTS`) and change what the agent offers, so they
are never open: the caller must send the owner's token as `Authorization: Bearer <token>`. The
token is `OWNER_TOKEN` in `code/.env`; without it every endpoint refuses. This is a stand-in
until owners authorise with their own key (see apps/owner/README.md).

What can change, and how it is checked, is node/settings.py; the version history is
node/deployments.py. A deploy needs the version the owner started from (`base_version`), so a
deploy from a stale page is refused (409) instead of overwriting a newer one.

The routes are their own small app, mounted at /owner, so the cross-origin access the owner
view needs (it is served from another port) is limited to them.
"""

import os
import secrets
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from apidocs import api_docs
from node.agent import DEFAULT_TOOLS, DEFAULT_WAKES_ON, PRIVATE_FACTS
from node.catalog import tools_for
from node.deployments import DeploymentStore
from node.settings import apply, canonical, validate

MAX_NOTE = 200


def keep_live_negotiation(raw, live: dict):
    """Owner input with the live negotiation limits filled in when `facts.negotiation` is left
    out: only an explicit null ends the bargaining (the owner view sends null and shows it as a
    change), so a partial draft never silently drops the floor."""
    if not isinstance(raw, dict) or not isinstance(raw.get("facts"), dict) or "negotiation" in raw["facts"]:
        return raw
    negotiation = live.get("facts", {}).get("negotiation")
    if negotiation is None:
        return raw
    return {**raw, "facts": {**raw["facts"], "negotiation": negotiation}}


def owner_app(config: dict, store: DeploymentStore, on_deploy: Callable[[], None]) -> FastAPI:
    """The owner app for one node. `config` is the node's live config, changed in place by a
    deploy; `on_deploy` tells the node's agent to re-read it."""
    app = FastAPI(title="Owner view API", **api_docs())
    # The token travels in a header, never a cookie, so open origins are safe.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"])

    def authorise(authorization: str | None) -> None:
        """Refuse unless the bearer token is the owner's token (compared in constant time)."""
        expected = os.environ.get("OWNER_TOKEN", "")
        if not expected:
            raise HTTPException(status_code=503, detail="owner access is not configured on this node (OWNER_TOKEN)")
        scheme, _, given = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(given.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="wrong or missing owner token")

    def overview_payload() -> dict:
        """The whole business as the owner sees it; `private` lists the facts no other agent sees."""
        spec = config.get("agent", {})
        current = store.current
        return {
            "node_id": config["node_id"],
            "name": config["name"],
            "uid": config.get("uid"),
            "kind": config.get("kind"),
            "capabilities": config.get("capabilities", []),
            "tags": config.get("tags", []),
            "seals": config.get("seals", []),
            "persona": spec.get("persona", {}),
            "tools": tools_for(spec.get("tools", DEFAULT_TOOLS)),
            "wakes_on": spec.get("wakes_on", DEFAULT_WAKES_ON),
            "facts": config.get("facts", {}),
            "private": list(PRIVATE_FACTS),
            "settings": current["settings"],
            "version": current["version"],
            "deployed_at": current["deployed_at"],
            "served_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    @app.get("/overview")
    def overview(authorization: str | None = Header(default=None)) -> dict:
        """The live business."""
        authorise(authorization)
        return overview_payload()

    @app.get("/versions")
    def versions(authorization: str | None = Header(default=None)) -> list[dict]:
        """Every version, newest first; version 0 is the original configuration."""
        authorise(authorization)
        return store.history()

    @app.post("/deploy")
    def deploy(body: dict = Body(...), authorization: str | None = Header(default=None)) -> dict:
        """Check and deploy settings; answers with the new live overview.

        422 {"detail": {"errors": [{path, message}]}} when a setting is not acceptable (or nothing
        changed), 409 when `base_version` is no longer the live version.
        """
        authorise(authorization)
        note = body.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE):
            raise HTTPException(status_code=422, detail={"errors": [{"path": "note", "message": f"at most {MAX_NOTE} characters"}]})
        with store.lock:
            live = store.current
            settings, errors = validate(keep_live_negotiation(body.get("settings"), live["settings"]))
            if not errors and live["settings"].get("facts", {}).get("rooms") \
                    and not any(room.available for room in settings.facts.rooms):
                errors = [{"path": "facts.rooms", "message": "keep at least one room available"}]
            if errors:
                raise HTTPException(status_code=422, detail={"errors": errors})
            if body.get("base_version") != live["version"]:
                raise HTTPException(status_code=409, detail=f"version {live['version']} is live now: "
                                                            "review the new state before deploying")
            if canonical(settings) == live["settings"]:
                raise HTTPException(status_code=422, detail={"errors": [{"path": "", "message": "nothing changed since the live version"}]})
            store.deploy(settings, note)  # written first: if it fails, nothing is applied
            apply(config, settings)
            on_deploy()
        return overview_payload()

    return app
