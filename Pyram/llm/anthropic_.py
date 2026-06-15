from __future__ import annotations

import json
import httpx

from .base import CompletionResponse, ToolCall, ToolResult, convert_tools_anthropic, convert_tool_choice_anthropic


class AnthropicResponse(CompletionResponse):
    def _parse(self):
        try:
            content_blocks = self._raw.get("content", [])
            text_parts = []
            thinking_text = ""
            raw_tools = []

            for block in content_blocks:
                btype = block.get("type", "")
                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "thinking":
                    thinking_text += block.get("thinking", "")
                elif btype == "tool_use":
                    raw_tools.append(block)

            self._content = "".join(text_parts)
            self._thinking = thinking_text

            if raw_tools:
                self._tool_calls = [ToolCall.from_anthropic(tc) for tc in raw_tools]
        except Exception:
            self._content = ""
            self._thinking = ""


class Anthropic:
    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        thinking: bool = False,
    ):
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.thinking = thinking
        self.base_url = "https://api.anthropic.com"

    def completetion(
        self,
        prompt: str = "",
        system: str = "voce e um agente de ia util",
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        messages: list[dict] | None = None,
    ):
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        if messages is None:
            msgs = [{"role": "user", "content": prompt}]
        else:
            msgs = _convert_messages_anthropic(messages)

        payload: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": msgs,
            "temperature": self.temperature,
        }

        if self.thinking:
            payload["thinking"] = {"type": "enabled"}

        converted = convert_tools_anthropic(tools)
        if converted:
            payload["tools"] = converted
        tc = convert_tool_choice_anthropic(tool_choice)
        if tc:
            payload["tool_choice"] = tc

        if system:
            payload["system"] = system

        response = httpx.post(
            f"{self.base_url}/v1/messages",
            headers=headers,
            json=payload,
            timeout=120.0,
        )

        raw = response.json()
        return AnthropicResponse(raw, self.thinking)


def _convert_messages_anthropic(messages: list[dict]) -> list[dict]:
    """Convert our unified message format to Anthropic format."""
    result = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            continue

        if role == "assistant" and msg.get("tool_calls"):
            blocks = []
            if content:
                blocks.append({"type": "text", "text": content})
            for tc in msg["tool_calls"]:
                blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": json.loads(tc["function"]["arguments"]),
                })
            result.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            result.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg["tool_call_id"],
                        "content": msg.get("content", ""),
                    }
                ],
            })
        else:
            result.append({"role": role, "content": content})

    return result
