"""r11: a hotel node that accepts the connection but hangs (overloaded, stuck worker).

Every MCP call (get_policies for each card in post_request, get_availability, and book right
after the Face ID approval) uses the MCP SDK's default client: 30 s to connect and a 300 s read
timeout (mcp/shared/_httpx_utils.py). The turn holds the conversation lock all that time, so the
wallet and voice sit silent for up to five minutes. HTTP calls elsewhere are capped at 20 s.
Expected: McpLink.call gives up after a short bound (here CALL_TIMEOUT_S, patched small) with
McpCallFailed, which the trust gate already turns into a calm "did not answer".
"""

import asyncio

import pytest

import assistant.mcp_client as mcp_client
from assistant.mcp_client import McpCallFailed, McpLink


class HangingClient:
    """An MCP client whose server accepted the call and never answers."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def call_tool(self, tool, args):
        await asyncio.sleep(3600)


def test_a_hung_hotel_fails_the_mcp_call_quickly(monkeypatch):
    monkeypatch.setattr(mcp_client, "CALL_TIMEOUT_S", 0.2, raising=False)
    monkeypatch.setattr(mcp_client, "COMMIT_TIMEOUT_S", 0.4, raising=False)  # book: longer, still bounded
    link = McpLink(lambda endpoint: HangingClient())

    async def run():
        return await asyncio.wait_for(link.call("http://hotel", "book", {}), 3)
    with pytest.raises(McpCallFailed):
        asyncio.run(run())
