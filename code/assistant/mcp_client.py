"""Tuttie's MCP client: calls a business's tools at <endpoint>/mcp/ (node/mcp_tools.py).

MCP is only the transport. A result is the business's signed envelope, and the Toolbox
verifies it (and the business's seals) before the LLM sees anything, as for every APS reply.
"""

import json
from collections.abc import Callable

from mcp import Client


class McpCallFailed(Exception):
    """The business could not be reached over MCP, or its tool failed without a signed answer."""


def connect_url(endpoint: str) -> Client:
    """An MCP client for the business at `endpoint` (its registry record's endpoint)."""
    return Client(f"{endpoint.rstrip('/')}/mcp/")


class McpLink:
    """Calls one tool per connection: MCP tools here are stateless, like the signed replies."""

    def __init__(self, connect: Callable[[str], Client] = connect_url):
        self.connect = connect  # tests and the headless demo connect to in-process servers

    async def call(self, endpoint: str, tool: str, args: dict) -> dict:
        """Call `tool` with `args`; returns the signed envelope the business sent."""
        try:
            async with self.connect(endpoint) as client:
                result = await client.call_tool(tool, args)
        except Exception as error:  # the SDK raises transport and protocol errors of many kinds
            raise McpCallFailed(f"{type(error).__name__}: {error}") from error
        text = result.content[0].text if result.content and result.content[0].type == "text" else ""
        if result.is_error:
            raise McpCallFailed(text or "tool failed")
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise McpCallFailed("answer is not JSON") from error
