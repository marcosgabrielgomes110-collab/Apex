from __future__ import annotations

import json
import httpx

from .base import CompletionResponse, ToolCall, ToolResult, ResponseCache, convert_tools


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
