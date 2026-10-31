"""counter_offer as an MCP tool (C4): the same checks and the same signed replies as over HTTP.

The tool function needs no MCP SDK; the round trip through a real MCP server and client runs
when the `mcp` package is installed (skipped otherwise).
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from nacl.signing import SigningKey

from aps import load_signing_key, sign_envelope, verify_envelope
from aps.keys import load_public_key
from negotiation.hotel import counter_offer_mcp_tool
from negotiation_helpers import CONFIGS, RHEINBLICK, TUTTIE, node_app, registry_lookup, signed_offer, stamp

NOW = datetime.now(timezone.utc)


def signed(payload: dict) -> dict:
    return sign_envelope(RHEINBLICK, payload, load_signing_key(RHEINBLICK))


def counter(offer: dict, round_: int, price: float, key: SigningKey | None = None, timestamp: str | None = None) -> dict:
    body = {"type": "counter", "offer_id": offer["payload"]["offer_id"], "round": round_, "price_chf": price,
            "includes": offer["payload"]["includes"], "conditions": offer["payload"]["conditions"]}
    return sign_envelope(TUTTIE, body, key or load_signing_key(TUTTIE), timestamp)


def strip(envelope: dict) -> dict:
    """The reply without what differs per signing (timestamp, signature)."""
    return envelope["payload"]


def test_the_mcp_tool_answers_like_the_http_route():
    tool = counter_offer_mcp_tool(CONFIGS[RHEINBLICK], signed, registry_lookup)
    client, offer = TestClient(node_app(RHEINBLICK)), signed_offer(add_ons=("dog",))
    cases = [counter(offer, 1, 175), counter(offer, 1, 175, key=SigningKey.generate()),
             counter(offer, 1, 175, timestamp=stamp(NOW - timedelta(hours=1)))]
    for envelope in cases:
        over_mcp = asyncio.run(tool(envelope, offer))
        over_http = client.post("/tools/counter_offer", json={"counter": envelope, "offer": offer, "last": None}).json()
        assert verify_envelope(over_mcp, load_public_key(RHEINBLICK), RHEINBLICK)
        assert strip(over_mcp) == strip(over_http)
    assert strip(asyncio.run(tool(cases[0], offer)))["price_chf"] == 189  # the pitch numbers hold
    assert strip(asyncio.run(tool(cases[1], offer)))["status"] == "refused"


def test_a_three_round_negotiation_over_a_real_mcp_server():
    pytest.importorskip("mcp")
    from mcp.client.client import Client
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(CONFIGS[RHEINBLICK]["name"])
    server.add_tool(counter_offer_mcp_tool(CONFIGS[RHEINBLICK], signed, registry_lookup), name="counter_offer")
    offer = signed_offer(add_ons=("dog",))  # 180 + 15

    async def run():
        async with Client(server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            schema = tools["counter_offer"].input_schema
            assert set(schema["properties"]) == {"counter", "offer", "last"}
            assert set(schema["required"]) == {"counter", "offer"}

            moves, last = [], None
            for round_, price in enumerate((175, 182, 185), start=1):
                result = await client.call_tool("counter_offer", {"counter": counter(offer, round_, price),
                                                                  "offer": offer, "last": last})
                reply = json.loads(result.content[0].text)
                assert not result.is_error and verify_envelope(reply, load_public_key(RHEINBLICK), RHEINBLICK)
                moves.append((price, reply["payload"]["type"], reply["payload"]["price_chf"]))
                last = reply

            forged = await client.call_tool("counter_offer", {"counter": counter(offer, 1, 175, key=SigningKey.generate()),
                                                              "offer": offer})
            return moves, json.loads(forged.content[0].text)["payload"]

    moves, refused = asyncio.run(run())
    assert moves == [(175, "counter", 189), (182, "counter", 187), (185, "agreement", 185)]  # as in test_negotiation_flow
    assert refused["status"] == "refused" and "signature does not verify" in refused["reason"]
