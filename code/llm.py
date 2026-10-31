"""The only module that talks to the LLM providers (OpenAI Responses API, Anthropic Messages API).

Shared by the assistant (tool loop) and the business nodes (their own A2A agents).
Callers use plain chat-style dicts ({"role", "content", "tool_calls"}, "tool"
messages); this module converts them, so swapping providers only touches this file.

The Responses API is used because reasoning models only allow function tools
together with reasoning there. Reasoning items are kept in the assistant message
under "provider_items" and sent back on the next turn; their readable summaries
are returned under "reasoning" so the UI can show the thinking process.

A model name starting with "claude-" (e.g. LLM_MODEL=claude-haiku-5-5) uses Anthropic's
Messages API instead, without thinking, for the fastest replies (ClaudeLLM below).
"""

import json
import os

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

CLAUDE_MAX_TOKENS = 4096    # Tuttie's answers are one to three sentences; tool calls are small
CLAUDE_EFFORTS = {"low", "medium", "high"}  # thinking can be off only up to "high"


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
    """Thin client for the OpenAI Responses API with optional reasoning settings.

    LLM("claude-...") (or LLM_MODEL=claude-...) returns a ClaudeLLM with the same methods.
    """

    def __new__(cls, model: str | None = None, reasoning: bool = True):
        """Pick the provider from the model name."""
        if (model or os.environ.get("LLM_MODEL", "")).startswith("claude-"):
            return ClaudeLLM(model)
        return super().__new__(cls)

    def __init__(self, model: str | None = None, reasoning: bool = True):
        """`reasoning=False` for a non-reasoning model (no reasoning options are sent)."""
        self.client = AsyncOpenAI()  # reads OPENAI_API_KEY
        self.model = model or os.environ.get("LLM_MODEL", "gpt-6-luna")
        self.options = {}
        if not reasoning:
            return
        reasoning = {}
        if effort := os.environ.get("LLM_REASONING_EFFORT"):  # e.g. "low"; unset = model default
            reasoning["effort"] = effort
        if summary := os.environ.get("LLM_REASONING_SUMMARY", "auto"):  # set empty for non-reasoning models
            reasoning["summary"] = summary
        self.options = {"reasoning": reasoning} if reasoning else {}

    async def complete(self, messages: list[dict], tools: list[dict], tool_choice: str | None = None) -> dict:
        """Return {"role", "content", "tool_calls"?, "reasoning": [summary texts], "provider_items"}.

        `tool_choice` names a tool the model must call in this turn.
        """
        forced = {"tool_choice": {"type": "function", "name": tool_choice}} if tool_choice else {}
        response = await self.client.responses.create(
            model=self.model, input=to_input(messages), tools=[to_tool(t) for t in tools], **self.options, **forced)
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


def to_claude(messages: list[dict]) -> tuple[str, list[dict]]:
    """Chat-style messages -> (system prompt, Messages API messages).

    Tool results become tool_result blocks, grouped into one user message per turn.
    """
    system, out = [], []
    for message in messages:
        role, content = message["role"], message.get("content")
        if role == "system":
            system.append(content)
        elif role == "assistant":
            out.append({"role": "assistant", "content": message.get("provider_items") or content or "..."})
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": message["tool_call_id"], "content": content}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        else:
            out.append({"role": "user", "content": content or ""})
    return "\n\n".join(system), out


def to_claude_tool(schema: dict) -> dict:
    """Chat-completions tool schema -> Messages API tool."""
    function = schema["function"]
    return {"name": function["name"], "description": function.get("description", ""),
            "input_schema": function.get("parameters") or {"type": "object", "properties": {}}}


class ClaudeLLM:
    """Same interface as LLM, on Anthropic's Messages API, with thinking off (fast)."""

    def __init__(self, model: str | None = None):
        """The key comes from ANTHROPIC_API_KEY; the effort from LLM_REASONING_EFFORT (default low)."""
        self.client = AsyncAnthropic()
        self.model = model or os.environ["LLM_MODEL"]
        effort = os.environ.get("LLM_REASONING_EFFORT", "")
        self.options = {"thinking": {"type": "disabled"},
                        "output_config": {"effort": effort if effort in CLAUDE_EFFORTS else "low"}}

    async def complete(self, messages: list[dict], tools: list[dict], tool_choice: str | None = None) -> dict:
        """Return {"role", "content", "tool_calls"?, "reasoning": [], "provider_items"} like LLM.complete."""
        system, chat = to_claude(messages)
        forced = {"tool_choice": {"type": "tool", "name": tool_choice}} if tool_choice else {}
        response = await self.client.messages.create(
            model=self.model, max_tokens=CLAUDE_MAX_TOKENS, system=system, messages=chat,
            tools=[to_claude_tool(t) for t in tools], **self.options, **forced)
        blocks = [block.model_dump(exclude_none=True) for block in response.content]
        text = "".join(b["text"] for b in blocks if b["type"] == "text").strip()
        result = {"role": "assistant", "content": text or None, "reasoning": [], "provider_items": blocks}
        calls = [b for b in blocks if b["type"] == "tool_use"]
        if calls:
            result["tool_calls"] = [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c["input"], ensure_ascii=False)}}
                for c in calls
            ]
        return result

    async def complete_json(self, system: str, user: str) -> dict:
        """One-shot completion that must return a JSON object."""
        response = await self.client.messages.create(
            model=self.model, max_tokens=CLAUDE_MAX_TOKENS, messages=[{"role": "user", "content": user}],
            system=f"{system}\n\nReply with one JSON object only, no other text.", **self.options)
        text = "".join(b.text for b in response.content if b.type == "text")
        return json.loads(text[text.find("{"):text.rfind("}") + 1] or "{}")
