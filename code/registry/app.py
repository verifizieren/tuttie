"""Registry service (port 4000): lets agents discover nodes by tag or capability.

The registry only serves signed records from data/registry.json. It does not
decide trust; the assistant verifies every seal itself.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

from apidocs import api_docs
from hosting import service_host

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "registry.json"

app = FastAPI(title="APS registry", **api_docs())


def load_records() -> list[dict]:
    """All registry records (read on every request, so a re-issued registry.json is live)."""
    return json.loads(REGISTRY_PATH.read_text())


@app.get("/search")
def search(tags: str = "", capability: str = "") -> list[dict]:
    """Records that carry all given tags (comma separated) and claim the capability."""
    wanted = {t.strip() for t in tags.split(",") if t.strip()}
    return [
        r for r in load_records()
        if wanted <= set(r["tags"]) and (not capability or capability in r["capabilities"])
    ]


@app.get("/nodes/{node_id}")
def get_node(node_id: str) -> dict:
    """One registry record by node id."""
    for record in load_records():
        if record["node_id"] == node_id:
            return record
    raise HTTPException(status_code=404, detail=f"unknown node {node_id}")


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(app, host=service_host(), port=int(os.environ.get("REGISTRY_PORT", "4000")))
