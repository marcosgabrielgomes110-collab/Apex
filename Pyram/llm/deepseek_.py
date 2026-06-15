from __future__ import annotations

import json
from typing import Generator

import httpx

from .base import CompletionResponse, StreamChunk, ToolCall, ToolResult, ResponseCache, convert_tools, _sse_chunks


class DeepSeekResponse(CompletionResponse):
    def _parse(self):
        try:
            choice = self._raw["choices"][0]
            msg = choice["message"]
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""
            raw_tools = msg.get("tool_calls")
        except (KeyError, IndexError):
            content = ""
            reasoning = ""
            raw_tools = None

        self._thinking = reasoning
        self._content = content

        if raw_tools:
            self._tool_calls = [ToolCall.from_openai(tc) for tc in raw_tools]


class DeepSeek:
    def __init__(
        self,
        model: str = "deepseek-v4-flash",
        api_key: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        thinking: bool = True,
        use_cache: bool = False,
    ):
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.thinking = thinking
        self.base_url = "https://api.deepseek.com"
        self._cache = ResponseCache("deepseek") if use_cache else None

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
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ]

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if self.thinking:
            payload["thinking"] = {"type": "enabled"}

        converted = convert_tools(tools)
        if converted:
            payload["tools"] = converted
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        if stream:
            payload["stream"] = True
            return self._stream(payload, headers)

        # cache check (apenas modo não-stream)
        if self._cache:
            cached = self._cache.get(payload)
            if cached:
                return DeepSeekResponse(cached, self.thinking)

        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120.0,
        )

        raw = response.json()
        if self._cache:
            self._cache.set(payload, raw)
        return DeepSeekResponse(raw, self.thinking)

    def _stream(self, payload: dict, headers: dict) -> Generator[StreamChunk, None, None]:
        url = f"{self.base_url}/chat/completions"
        acc_tools: dict[int, dict] = {}

        with httpx.Client() as client:
            with client.stream("POST", url, headers=headers, json=payload, timeout=120) as resp:
                for _, data in _sse_chunks(resp):
                    chunk = self._parse_chunk(data, acc_tools)
                    if chunk:
                        yield chunk

    def _parse_chunk(self, data: dict, acc_tools: dict[int, dict]) -> StreamChunk | None:
        choices = data.get("choices")
        if not choices:
            return None
        choice = choices[0]
        delta = choice.get("delta", {})
        finish = choice.get("finish_reason")

        content = delta.get("content") or ""
        reasoning = delta.get("reasoning_content") or ""
        raw_tcs = delta.get("tool_calls")

        # acumula tool calls parciais por índice
        if raw_tcs:
            for tc in raw_tcs:
                idx = tc.get("index", 0)
                if idx not in acc_tools:
                    acc_tools[idx] = {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                acc = acc_tools[idx]
                if tc.get("id"):
                    acc["id"] = tc["id"]
                fn = tc.get("function", {})
                if fn.get("name"):
                    acc["function"]["name"] = fn["name"]
                if fn.get("arguments"):
                    acc["function"]["arguments"] += fn["arguments"]

        completed_tcs = None
        if finish and acc_tools:
            completed_tcs = [ToolCall.from_openai(acc_tools[i]) for i in sorted(acc_tools)]

        if content or reasoning or completed_tcs or finish:
            return StreamChunk(
                content=content,
                thinking=reasoning,
                tool_calls=completed_tcs,
                done=bool(finish),
                finish_reason=finish,
            )

        return None
