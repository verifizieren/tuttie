"""Marketplace service (port 4010): the HTTP face of marketplace.market.Market.

POST /postings                       a user agent's signed Request (envelope)
POST /postings/{request_id}/offers   a business's signed Offer (envelope)
GET  /postings/{request_id}          the posting, who was invited and all accepted offers

Run from code/: python -m marketplace.app
"""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request as HttpRequest
from fastapi.responses import JSONResponse

from aps.keys import load_public_key
from marketplace.market import Market, MarketError

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("MARKETPLACE_PORT", "4010"))
REGISTRY_URL = os.environ.get("REGISTRY_URL", f"http://localhost:{os.environ.get('REGISTRY_PORT', '4000')}")
PUBLIC_URL = os.environ.get("MARKETPLACE_URL", f"http://localhost:{PORT}")


def load_authorities() -> dict:
    """The trusted authorities from data/authorities.json, by issuer id."""
    return {a["issuer"]: a for a in json.loads((ROOT / "data" / "authorities.json").read_text())}


def create_app(http: httpx.AsyncClient | None = None) -> FastAPI:
    """The marketplace app; tests pass an httpx client with a mock transport."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = http or httpx.AsyncClient(timeout=10)
        app.state.market = Market(client, REGISTRY_URL, load_authorities(), load_public_key("user"), PUBLIC_URL)
        yield
        if http is None:
            await client.aclose()

    app = FastAPI(title="Tuttie marketplace", lifespan=lifespan)

    @app.exception_handler(MarketError)
    async def refused(_: HttpRequest, error: MarketError) -> JSONResponse:
        """Every refusal says why, so the sender's agent can show or fix it."""
        return JSONResponse({"refused": True, "reason": error.reason}, status_code=error.status)

    @app.post("/postings", status_code=201)
    async def post_request(envelope: dict) -> dict:
        """Accept a signed request and wake the matching business agents."""
        return await app.state.market.post_request(envelope)

    @app.post("/postings/{request_id}/offers", status_code=201)
    async def post_offer(request_id: str, envelope: dict) -> dict:
        """Accept a signed offer from an invited business."""
        return await app.state.market.receive_offer(request_id, envelope)

    @app.get("/postings/{request_id}")
    def get_posting(request_id: str) -> dict:
        """The posting, the invited businesses and every accepted offer."""
        return app.state.market.view(request_id)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
