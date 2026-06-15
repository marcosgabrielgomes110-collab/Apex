from __future__ import annotations

import json
from typing import Generator

import httpx

from .base import CompletionResponse, StreamChunk, ToolCall, ToolResult, convert_tools_anthropic, convert_tool_choice_anthropic, _sse_chunks


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
        stream: bool = False,
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

        if stream:
            payload["stream"] = True
            return self._stream(payload, headers)

        response = httpx.post(
            f"{self.base_url}/v1/messages",
            headers=headers,
            json=payload,
            timeout=120.0,
        )

        raw = response.json()
        return AnthropicResponse(raw, self.thinking)

    def _stream(self, payload: dict, headers: dict) -> Generator[StreamChunk, None, None]:
        url = f"{self.base_url}/v1/messages"
        # estado para blocos de conteúdo incremental
        blocks: dict[int, dict] = {}
        finish_reason: str | None = None

        with httpx.Client() as client:
            with client.stream("POST", url, headers=headers, json=payload, timeout=120) as resp:
                for event_type, data in _sse_chunks(resp):
                    chunk = self._parse_chunk(event_type, data, blocks, finish_reason)
                    if chunk:
                        yield chunk

    def _parse_chunk(
        self, event_type: str | None, data: dict, blocks: dict[int, dict],
        finish_reason: str | None
    ) -> StreamChunk | None:
        if event_type == "content_block_start":
            idx = data.get("index", 0)
            block = data.get("content_block", {})
            blocks[idx] = {"type": block.get("type", ""), "text": "", "thinking": ""}
            if block.get("type") == "tool_use":
                blocks[idx].update({
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "input": block.get("input", ""),
                })
            return None

        if event_type == "content_block_delta":
            idx = data.get("index", 0)
            delta = data.get("delta", {})
            dtype = delta.get("type", "")
            if idx not in blocks:
                return None
            if dtype == "text_delta":
                blocks[idx]["text"] += delta.get("text", "")
                text = delta.get("text", "")
                return StreamChunk(content=text)
            if dtype == "thinking_delta":
                blocks[idx]["thinking"] += delta.get("thinking", "")
                return StreamChunk(thinking=delta.get("thinking", ""))
            return None

        if event_type == "content_block_stop":
            idx = data.get("index", 0)
            block = blocks.get(idx, {})
            if block.get("type") == "tool_use" and block.get("name"):
                tc = ToolCall(
                    id=block.get("id", ""),
                    type="tool_use",
                    name=block.get("name", ""),
                    arguments=json.dumps(block.get("input", {}), ensure_ascii=False),
                )
                return StreamChunk(tool_calls=[tc])
            return None

        if event_type == "message_delta":
            delta = data.get("delta", {})
            fr = delta.get("stop_reason")
            # fr pode ser "end_turn", "max_tokens", "stop_sequence", "tool_use"
            return StreamChunk(done=True, finish_reason=fr)

        if event_type == "message_stop":
            return None  # já sinalizado em message_delta

        return None


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
