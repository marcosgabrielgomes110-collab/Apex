from __future__ import annotations

import json
from typing import Generator

import httpx

from .base import CompletionResponse, StreamChunk, ToolCall, convert_tools, convert_tool_choice_cohere, _sse_chunks


class CohereResponse(CompletionResponse):
    def _parse(self):
        try:
            msg = self._raw.get("message", {})
            content_blocks = msg.get("content", [])
            text_parts = []

            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)

            self._content = "".join(text_parts)

            # Cohere thinking
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    self._thinking = block.get("thinking", "")

            raw_tools = msg.get("tool_calls") or []
            if raw_tools:
                self._tool_calls = [ToolCall.from_cohere(tc) for tc in raw_tools]
        except Exception:
            self._content = ""


class Cohere:
    def __init__(
        self,
        model: str = "command-nightly",
        api_key: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.3,
        thinking: bool = False,
    ):
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.thinking = thinking
        self.base_url = "https://api.cohere.com"

    def completetion(
        self,
        prompt: str = "",
        system: str = "voce e um agente de ia util",
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
        messages: list[dict] | None = None,
        stream: bool = False,
    ):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        if messages is None:
            msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ]
        else:
            msgs = _convert_messages_cohere(messages)

        payload: dict = {
            "model": self.model,
            "messages": msgs,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

        if self.thinking:
            payload["thinking"] = {"type": "enabled"}

        converted = convert_tools(tools)
        if converted:
            payload["tools"] = converted
        tc = convert_tool_choice_cohere(tool_choice)
        if tc:
            payload["tool_choice"] = tc

        if stream:
            return self._stream(payload, headers)

        response = httpx.post(
            f"{self.base_url}/v2/chat",
            headers=headers,
            json=payload,
            timeout=120.0,
        )

        raw = response.json()
        return CohereResponse(raw, self.thinking)

    def _stream(self, payload: dict, headers: dict) -> Generator[StreamChunk, None, None]:
        url = f"{self.base_url}/v2/chat"
        # Cohere v2 envia tool_calls apenas no evento stream-end
        tool_calls_collected = []

        with httpx.Client() as client:
            with client.stream("POST", url, headers=headers, json=payload, timeout=120) as resp:
                for event_type, data in _sse_chunks(resp):
                    chunk = self._parse_chunk(event_type, data, tool_calls_collected)
                    if chunk:
                        yield chunk

    def _parse_chunk(
        self, event_type: str | None, data: dict,
        tool_calls_collected: list
    ) -> StreamChunk | None:
        if event_type == "text-generation":
            text = data.get("text", "")
            if text:
                return StreamChunk(content=text)
            return None

        if event_type == "stream-end":
            resp = data.get("response", {})
            finish = resp.get("finish_reason")
            msg = resp.get("message", {})
            raw_tcs = msg.get("tool_calls") or []

            tcs = None
            if raw_tcs:
                tcs = [ToolCall.from_cohere(tc) for tc in raw_tcs]

            return StreamChunk(
                done=True,
                finish_reason=finish,
                tool_calls=tcs,
            )

        return None


def _convert_messages_cohere(messages: list[dict]) -> list[dict]:
    """Convert unified messages to Cohere v2 format."""
    result = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "assistant" and msg.get("tool_calls"):
            tcs = []
            if content:
                tcs.append({"type": "text", "text": content})
            for tc in msg["tool_calls"]:
                tcs.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                })
            result.append({"role": "assistant", "content": content, "tool_calls": tcs})
        elif role == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": msg["tool_call_id"],
                "content": content,
            })
        else:
            result.append({"role": role, "content": content})

    return result
