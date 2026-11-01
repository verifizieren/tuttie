"""Tuttie's MCP client: calls a business's tools at <endpoint>/mcp/ (node/mcp_tools.py).

MCP is only the transport. A result is the business's signed envelope, and the Toolbox
verifies it (and the business's seals) before the LLM sees anything, as for every APS reply.
"""

import asyncio
import json
import math
from collections.abc import Callable

from mcp import Client

CALL_TIMEOUT_S = 15  # the SDK waits up to 300 s; a hung hotel must not hold the turn that long
# book and pay commit at the hotel: they get longer than the node's own registry lookup (20 s),
# so Tuttie never reports a failure while the hotel still finishes the booking.
COMMIT_TIMEOUT_S = 30


class McpCallFailed(Exception):
    """The business could not be reached over MCP, or its tool failed without a signed answer."""


def finite_float(text: str) -> float:
    """A JSON number as float, refusing ones too big to be finite (1e309 would be Infinity)."""
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"{text} is not a finite number")
    return value


def reject_constant(name: str):
    """json.loads hook: NaN and Infinity are not JSON, so a reply holding them is refused."""
    raise ValueError(f"{name} is not JSON")


def connect_url(endpoint: str) -> Client:
    """An MCP client for the business at `endpoint` (its registry record's endpoint)."""
    return Client(f"{endpoint.rstrip('/')}/mcp/")


class McpLink:
    """Calls one tool per connection: MCP tools here are stateless, like the signed replies."""

    def __init__(self, connect: Callable[[str], Client] = connect_url):
        self.connect = connect  # tests and the headless demo connect to in-process servers

    async def call(self, endpoint: str, tool: str, args: dict) -> dict:
        """Call `tool` with `args`; returns the signed envelope the business sent."""
        async def once():
            async with self.connect(endpoint) as client:
                return await client.call_tool(tool, args)
        try:
            result = await asyncio.wait_for(once(), COMMIT_TIMEOUT_S if tool in ("book", "pay") else CALL_TIMEOUT_S)
        except Exception as error:  # the SDK raises transport and protocol errors of many kinds (and TimeoutError)
            raise McpCallFailed(f"{type(error).__name__}: {error}") from error
        text = result.content[0].text if result.content and result.content[0].type == "text" else ""
        if result.is_error:
            raise McpCallFailed(text or "tool failed")
        try:
            return json.loads(text, parse_float=finite_float, parse_constant=reject_constant)
        except ValueError as error:  # also json.JSONDecodeError
            raise McpCallFailed("answer is not JSON") from error
