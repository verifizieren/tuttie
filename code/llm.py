"""The only module that talks to the LLM provider (OpenAI Responses API).

Shared by the assistant (tool loop) and the business nodes (their own A2A agents).
Callers use plain chat-style dicts ({"role", "content", "tool_calls"}, "tool"
messages); this module converts them, so swapping providers only touches this file.

The Responses API is used because reasoning models only allow function tools
together with reasoning there. Reasoning items are kept in the assistant message
under "provider_items" and sent back on the next turn; their readable summaries
are returned under "reasoning" so the UI can show the thinking process.
"""

import json
import os

from openai import AsyncOpenAI


def to_input(messages: list[dict]) -> list[dict]:
    """Chat-style messages -> Responses API input items."""
    items = []
    for message in messages:
        if message["role"] == "assistant" and "provider_items" in message:
            items.extend(message["provider_items"])
        elif message["role"] == "tool":
            items.append({"type": "function_call_output", "call_id": message["tool_call_id"],
                          "output": message["content"]})
        else:
            items.append({"role": message["role"], "content": message["content"] or ""})
    return items


def to_tool(schema: dict) -> dict:
    """Chat-completions tool schema -> Responses API tool."""
    return {"type": "function", **schema["function"]}


class LLM:
    def __init__(self, model: str | None = None):
        self.client = AsyncOpenAI()  # reads OPENAI_API_KEY
        self.model = model or os.environ.get("LLM_MODEL", "gpt-6-luna")
        reasoning = {}
        if effort := os.environ.get("LLM_REASONING_EFFORT"):  # e.g. "low"; unset = model default
            reasoning["effort"] = effort
        if summary := os.environ.get("LLM_REASONING_SUMMARY", "auto"):  # set empty for non-reasoning models
            reasoning["summary"] = summary
        self.options = {"reasoning": reasoning} if reasoning else {}

    async def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return {"role", "content", "tool_calls"?, "reasoning": [summary texts], "provider_items"}."""
        response = await self.client.responses.create(
            model=self.model, input=to_input(messages), tools=[to_tool(t) for t in tools], **self.options)
        items = [item.model_dump(exclude_none=True) for item in response.output]
        summaries = [part["text"] for item in items if item["type"] == "reasoning"
                     for part in item.get("summary", []) if part.get("text")]
        result = {"role": "assistant", "content": response.output_text or None,
                  "reasoning": summaries, "provider_items": items}
        calls = [item for item in items if item["type"] == "function_call"]
        if calls:
            result["tool_calls"] = [
                {"id": c["call_id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                for c in calls
            ]
        return result

    async def complete_json(self, system: str, user: str) -> dict:
        """One-shot completion that must return a JSON object."""
        response = await self.client.responses.create(
            model=self.model,
            input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            text={"format": {"type": "json_object"}},
            **self.options,
        )
        return json.loads(response.output_text or "{}")
