"""The user agent's side of the marketplace: sign a request and post it.

Tuttie signs with its own key (keys/<agent id>.json), never with the user's: its
delegation in the registry proves that it acts for the user. Used by the assistant
(and Tuttie's subagents) to put up postings.
"""

import secrets

import httpx
from nacl.signing import SigningKey

from aps import sign_envelope
from marketplace.messages import Request


def new_request_id() -> str:
    """A fresh request id in the Request format (rq-<8 hex>)."""
    return f"rq-{secrets.token_hex(4)}"


def sign_request(request: Request, agent_id: str, agent_key: SigningKey) -> dict:
    """The request as a signed envelope from the user agent."""
    return sign_envelope(agent_id, request.model_dump(mode="json"), agent_key)


async def post_request(http: httpx.AsyncClient, market_url: str, envelope: dict) -> dict:
    """Post a signed request; returns the posting with who was invited.

    Raises httpx.HTTPStatusError with the market's reason if it refuses the request.
    """
    response = await http.post(f"{market_url.rstrip('/')}/postings", json=envelope)
    response.raise_for_status()
    return response.json()
