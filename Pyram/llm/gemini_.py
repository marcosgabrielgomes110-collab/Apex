from __future__ import annotations

from typing import Generator

import httpx

from .base import CompletionResponse, StreamChunk, ToolCall, convert_tools_gemini, convert_tool_choice_gemini, _sse_chunks


class GeminiResponse(CompletionResponse):
    def _parse(self):
        try:
            candidate = self._raw["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            text_parts = []
            raw_functions = []

            for part in parts:
                if "text" in part:
                    text_parts.append(part["text"])
                if "functionCall" in part:
                    raw_functions.append(part["functionCall"])

            self._content = "".join(text_parts)

            if raw_functions:
                self._tool_calls = [ToolCall.from_gemini(fc) for fc in raw_functions]
        except (KeyError, IndexError):
            self._content = ""


class Gemini:
    def __init__(
        self,
        model: str = "gemini-3.5-flash",
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
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

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
            "x-goog-api-key": self.api_key,
        }

        if messages is None:
            contents = [{"parts": [{"text": prompt}]}]
        else:
            contents = _convert_messages_gemini(messages)

        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": self.max_tokens,
                "temperature": self.temperature,
            },
        }

        if system:
            payload["systemInstruction"] = {
                "role": "user",
                "parts": [{"text": system}],
            }

        converted = convert_tools_gemini(tools)
        if converted:
            payload["tools"] = converted
        tc = convert_tool_choice_gemini(tool_choice)
        if tc:
            payload["toolConfig"] = tc

        if stream:
            return self._stream(payload, headers)

        response = httpx.post(
            f"{self.base_url}/models/{self.model}:generateContent",
            headers=headers,
            json=payload,
            timeout=120.0,
        )

        raw = response.json()
        return GeminiResponse(raw, self.thinking)

    def _stream(self, payload: dict, headers: dict) -> Generator[StreamChunk, None, None]:
        url = f"{self.base_url}/models/{self.model}:streamGenerateContent"

        with httpx.Client() as client:
            with client.stream("POST", url, headers=headers, json=payload, timeout=120) as resp:
                for _, data in _sse_chunks(resp):
                    chunk = self._parse_chunk(data)
                    if chunk:
                        yield chunk

    def _parse_chunk(self, data: dict) -> StreamChunk | None:
        candidates = data.get("candidates")
        if not candidates:
            return None
        c = candidates[0]
        parts = c.get("content", {}).get("parts", [])

        content = ""
        tcs = None

        for part in parts:
            if "text" in part:
                content += part["text"]
            if "functionCall" in part:
                fc = part["functionCall"]
                tc = ToolCall.from_gemini(fc)
                if tcs is None:
                    tcs = []
                tcs.append(tc)

        finish = c.get("finishReason")
        if content or tcs or finish:
            return StreamChunk(
                content=content,
                tool_calls=tcs,
                done=bool(finish),
                finish_reason=finish,
            )

        return None


def _convert_messages_gemini(messages: list[dict]) -> list[dict]:
    """Convert unified messages to Gemini contents format."""
    result = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            continue

        if role == "assistant" and msg.get("tool_calls"):
            parts = []
            if content:
                parts.append({"text": content})
            for tc in msg["tool_calls"]:
                parts.append({
                    "functionCall": {
                        "name": tc["function"]["name"],
                        "args": tc["function"]["arguments"],
                    }
                })
            result.append({"role": "model", "parts": parts})
        elif role == "tool":
            result.append({
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": msg.get("name", ""),
                            "response": {"result": msg.get("content", "")},
                        }
                    }
                ],
            })
        else:
            gemini_role = "model" if role == "assistant" else "user"
            result.append({"role": gemini_role, "parts": [{"text": content}]})

    return result
