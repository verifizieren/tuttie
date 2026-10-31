"""Whether a FastAPI app serves its API docs (/docs, /redoc, /openapi.json).

Off by default: on the public server they would list every internal endpoint. Set API_DOCS=1
for local development to get them back. Every app passes `**api_docs()` to FastAPI(...).
"""

import os


def api_docs() -> dict:
    """FastAPI keyword arguments: the default doc URLs with API_DOCS=1, none otherwise."""
    if os.environ.get("API_DOCS", "").strip().lower() in {"1", "true", "yes", "on"}:
        return {}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}
