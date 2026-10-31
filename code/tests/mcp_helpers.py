"""Helpers to call a node's MCP tools in-process, as Tuttie would over HTTP."""

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from mcp import Client

from aps import load_signing_key
from aps.call import sign_call
from assistant.mcp_client import McpLink

REGISTRY = json.loads((Path(__file__).resolve().parent.parent / "data" / "registry.json").read_text())
TUTTIE = "ch.tuttie.alex-muster"


async def registry_record(node_id: str) -> dict | None:
    """Look up a node in the demo registry without a running registry service."""
    return next((r for r in REGISTRY if r["node_id"] == node_id), None)


def call_tool(app: FastAPI, tool: str, args: dict | None = None) -> dict:
    """Call one MCP tool of a node app and return its signed envelope."""
    return asyncio.run(McpLink(lambda _: Client(app.state.mcp)).call("in-process", tool, args or {}))


def signed_book(app: FastAPI, args: dict, agent_id: str = TUTTIE, key=None) -> dict:
    """Book through MCP with a call signed by Tuttie (or `key`); returns the signed payload."""
    call = sign_call("book", args, agent_id, key or load_signing_key(agent_id))
    return call_tool(app, "book", {"call": call})["payload"]


def in_process_link(apps_by_endpoint: dict[str, FastAPI]) -> McpLink:
    """An McpLink that reaches each endpoint's node app in-process."""
    return McpLink(lambda endpoint: Client(apps_by_endpoint[endpoint].state.mcp))
