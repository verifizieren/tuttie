"""The only module that talks to the LLM provider (OpenAI chat completions).

Shared by the assistant (tool loop) and the business nodes (their own A2A agents).

Swap providers by reimplementing LLM.complete and LLM.complete_json; callers only
see plain dicts.
"""

import json
import os

from openai import AsyncOpenAI


class LLM:
    def __init__(self, model: str | None = None):
        self.client = AsyncOpenAI()  # reads OPENAI_API_KEY
        self.model = model or os.environ.get("LLM_MODEL", "gpt-4.1")

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

    async def complete_json(self, system: str, user: str) -> dict:
        """One-shot completion that must return a JSON object."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content or "{}")
