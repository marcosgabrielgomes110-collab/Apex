from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any

from ..configs import Cache


@dataclass
class ToolCall:
    id: str
    type: str = "function"
    name: str = ""
    arguments: str = ""

    @classmethod
    def from_openai(cls, tc: dict) -> ToolCall:
        return cls(
            id=tc.get("id", ""),
            type=tc.get("type", "function"),
            name=tc["function"]["name"],
            arguments=tc["function"]["arguments"],
        )

    @classmethod
    def from_gemini(cls, fc: dict) -> ToolCall:
        return cls(
            id=fc.get("id", ""),
            type="function",
            name=fc.get("name", ""),
            arguments=json.dumps(fc.get("args", {}), ensure_ascii=False),
        )

    @classmethod
    def from_anthropic(cls, block: dict) -> ToolCall:
        inp = block.get("input", {})
        return cls(
            id=block.get("id", ""),
            type="tool_use",
            name=block.get("name", ""),
            arguments=json.dumps(inp, ensure_ascii=False),
        )

    @classmethod
    def from_cohere(cls, tc: dict) -> ToolCall:
        return cls(
            id=tc.get("id", ""),
            type=tc.get("type", "function"),
            name=tc["function"]["name"],
            arguments=tc["function"]["arguments"],
        )

    def to_openai_message(self) -> dict:
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": self.id,
                    "type": self.type,
                    "function": {"name": self.name, "arguments": self.arguments},
                }
            ],
        }

    def to_gemini_content(self) -> dict:
        return {
            "role": "model",
            "parts": [
                {
                    "functionCall": {
                        "name": self.name,
                        "args": json.loads(self.arguments),
                    }
                }
            ],
        }

    def to_anthropic_content_block(self) -> dict:
        return {
            "type": "tool_use",
            "id": self.id,
            "name": self.name,
            "input": json.loads(self.arguments),
        }


@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    content: str

    def to_openai_message(self) -> dict:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.content,
        }

    def to_gemini_content(self) -> dict:
        return {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": self.name,
                        "id": self.tool_call_id,
                        "response": {"result": self.content},
                    }
                }
            ],
        }

    def to_anthropic_content_block(self) -> dict:
        return {
            "type": "tool_result",
            "tool_use_id": self.tool_call_id,
            "content": self.content,
        }

    def to_cohere_message(self) -> dict:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.content,
        }


class CompletionResponse:
    def __init__(self, raw: dict, thinking_enabled: bool = False):
        self._raw = raw
        self._thinking_enabled = thinking_enabled
        self._content: str = ""
        self._thinking: str = ""
        self._tool_calls: list[ToolCall] = []
        self._parse()

    def _parse(self) -> None:
        raise NotImplementedError

    @property
    def content(self) -> str:
        return self._content

    @property
    def tool_calls(self) -> list[ToolCall]:
        return self._tool_calls

    @property
    def thinking(self) -> str:
        return self._thinking

    def text(self) -> str:
        result = ""
        if self._thinking_enabled and self._thinking:
            result += f"thinkink >> {self._thinking}\n"
        result += f"response >> {self._content}"
        return result

    def jsn(self) -> dict:
        return self._raw


def convert_tools(tools: list[dict] | None) -> Any:
    """Return tools as-is (OpenAI/Groq format)."""
    return tools


def convert_tools_anthropic(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    result = []
    for t in tools:
        if t.get("type") == "function":
            fn = t.get("function", {})
            result.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
    return result if result else None


def convert_tools_gemini(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    declarations = []
    for t in tools:
        if t.get("type") == "function":
            fn = t.get("function", {})
            declarations.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
            })
    return [{"functionDeclarations": declarations}] if declarations else None


def convert_tool_choice(choice: str | dict | None) -> str | dict | None:
    return choice


def convert_tool_choice_anthropic(choice: str | dict | None) -> dict | None:
    if choice is None or choice == "auto":
        return {"type": "auto"}
    if choice == "any" or choice == "required":
        return {"type": "any"}
    if choice == "none":
        return {"type": "none"}
    if isinstance(choice, dict):
        name = choice.get("function", {}).get("name", "")
        return {"type": "tool", "name": name} if name else {"type": "any"}
    return None


def convert_tool_choice_gemini(choice: str | dict | None) -> dict | None:
    if choice is None or choice == "auto":
        return None
    if choice == "none":
        return {"functionCallingConfig": {"mode": "NONE"}}
    if choice == "any" or choice == "required":
        return {"functionCallingConfig": {"mode": "ANY"}}
    if isinstance(choice, dict):
        name = choice.get("function", {}).get("name", "")
        return {
            "functionCallingConfig": {
                "mode": "ANY",
                "allowed_function_names": [name],
            }
        }
    return None


def convert_tool_choice_cohere(choice: str | dict | None) -> str | None:
    if choice is None or choice == "auto":
        return None
    if choice == "none":
        return "NONE"
    if choice == "any" or choice == "required":
        return "REQUIRED"
    if isinstance(choice, dict):
        return "REQUIRED"
    return None


class ResponseCache(Cache):
    """Cache de respostas LLM. Wrapper de Cache com namespace 'responses/{provider}'."""

    def __init__(self, provider: str, ttl: int = 3600):
        super().__init__(f"responses/{provider}", ttl=ttl)
