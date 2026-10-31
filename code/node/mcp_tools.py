"""A business's tools as an MCP server (Model Context Protocol), mounted at /mcp/ on its node.

Any MCP client can list and call the tools. Every result is the node's signed envelope (sent
as JSON text), so the caller verifies it like any APS reply.

Reading tools (get_availability, get_policies) are open. An action (book) runs only with a
call signed by the calling agent (aps/call.py, "Signed call" in documentation/formats.md):
the caller's key comes from its registry record, never from the call; each call is accepted
once (NonceBook); and the arguments it signs are exactly what the action gets, so the
approval and the amount inside cannot be swapped. Whether the action is allowed (the user's
approval, the hotel's agreement or commitments) is then checked by the action itself.
"""

from collections.abc import Awaitable, Callable

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, ValidationError

from aps.call import NonceBook, verify_call

INSTRUCTIONS = ("Tools of one business on the agent web. Every result is a signed envelope "
                "(node_id, timestamp, payload, signature): verify it against the business's registry "
                "record before using it. Actions need a signed call (aps/call.py).")


def mcp_server(name: str, signed: Callable[[dict], dict], tools: dict[str, Callable],
               book_request: type[BaseModel], lookup: Callable[[str], Awaitable[dict | None]]) -> MCPServer:
    """The MCP server for one node.

    `tools` holds the node's own functions: get_availability(date, guests), get_policies() and
    book(request, checked), each returning a signed envelope. `lookup` finds a caller's
    registry record.
    """
    server = MCPServer(name, instructions=INSTRUCTIONS)
    nonces = NonceBook()

    @server.tool(name="get_availability")
    def get_availability(date: str, guests: int = 1) -> dict:
        """Available rooms and prices for a date (YYYY-MM-DD), signed by the business."""
        return tools["get_availability"](date, guests)

    @server.tool(name="get_policies")
    def get_policies() -> dict:
        """Who the business is, location, quietness, dogs, check-in and cancellation, signed."""
        return tools["get_policies"]()

    @server.tool(name="book")
    async def book(call: dict) -> dict:
        """Book a room. `call` is a signed call for tool "book" whose args are date, room_type,
        guest_name, extras (this business's signed commitments), approval (the user's signed
        decision for exactly the total) and optionally agreement (this business's signed deal)."""
        def refuse(reason: str) -> dict:
            return signed({"tool": "book", "status": "refused", "reason": reason})

        record = await lookup(call.get("agent_id", "")) if isinstance(call.get("agent_id"), str) else None
        if record is None:
            return refuse("caller is not in the registry")
        if not verify_call(call, record["public_key"], tool="book"):
            return refuse("call is not signed by the caller, is outdated or is for another tool")
        if not nonces.use(call["agent_id"], call["nonce"]):
            return refuse("call was already used")
        try:
            request = book_request(**call["args"])
        except ValidationError as error:
            return refuse(f"invalid arguments: {error.errors()[0]['msg']}")
        return tools["book"](request, ["caller signature"])

    return server


def mcp_app(server: MCPServer):
    """The server's Streamable HTTP app, to mount at /mcp on the node.

    Stateless with plain JSON answers: every call stands alone, like the signed tools themselves.
    A business is a public service that any agent may reach, so the host check against DNS
    rebinding (meant for servers on a user's own machine) is not used.
    """
    return server.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True,
                                      host="0.0.0.0")
