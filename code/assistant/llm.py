"""The only module that talks to the LLM provider (OpenAI chat completions with tools).

Swap providers by reimplementing LLM.complete; the rest of the assistant only sees
plain chat messages as dicts.
"""

import os

from openai import AsyncOpenAI


class LLM:
    def __init__(self, model: str | None = None):
        self.client = AsyncOpenAI()  # reads OPENAI_API_KEY
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4.1-mini")

    async def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return the assistant message: {"role", "content", "tool_calls"?}."""
        response = await self.client.chat.completions.create(model=self.model, messages=messages, tools=tools)
        message = response.choices[0].message
        result = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            result["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in message.tool_calls
            ]
        return result
