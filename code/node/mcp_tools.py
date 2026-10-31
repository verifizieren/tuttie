"""A business's tools as an MCP server (Model Context Protocol), mounted at /mcp/ on its node.

Any MCP client can list and call the tools. Every result is the node's signed envelope (sent
as JSON text), so the caller verifies it like any APS reply.

Reading tools (get_availability, get_policies) are open. Actions (book) take a call signed by
the calling agent (aps/call.py, "Signed call" in documentation/formats.md) and run only if it
passes the action gate (aps/gate.py) on the node. Bargaining (counter_offer) brings its own
checks (negotiation/hotel.py). This module only describes the tools; the node does the work.
"""

from collections.abc import Callable

from mcp.server.mcpserver import MCPServer

INSTRUCTIONS = ("Tools of one business on the agent web. Every result is a signed envelope "
                "(node_id, timestamp, payload, signature): verify it against the business's registry "
                "record before using it. Actions need a signed call (aps/call.py).")


def mcp_server(name: str, tools: dict[str, Callable], extra: dict[str, Callable] | None = None) -> MCPServer:
    """The MCP server for one node.

    `tools` holds the node's own functions, each returning a signed envelope:
    get_availability(date, guests), get_policies() and async book(call). `extra` are ready-made
    tool functions registered as they are (their parameters and docstring describe them).
    """
    server = MCPServer(name, instructions=INSTRUCTIONS)

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
        """Book a room. `call` is a signed call (tool "book", signed by a sealed user agent with the
        user's delegation for "book") whose args are date, room_type, guest_name, extras (this
        business's signed commitments), approval (the user's signed decision for exactly the
        total) and optionally agreement (this business's signed deal, replacing the total).
        Returns the signed confirmation with the checks it passed, or a signed refusal."""
        return await tools["book"](call)

    for tool_name, function in (extra or {}).items():
        server.add_tool(function, name=tool_name)
    return server


def mcp_app(server: MCPServer):
    """The server's Streamable HTTP app, to mount at /mcp on the node.

    Stateless with plain JSON answers: every call stands alone, like the signed tools themselves.
    A business is a public service that any agent may reach, so the host check against DNS
    rebinding (meant for servers on a user's own machine) is not used.
    """
    return server.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True,
                                      host="0.0.0.0")
