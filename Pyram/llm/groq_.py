from __future__ import annotations

from .openai_ import OpenAI, OpenAIResponse


class Groq(OpenAI):
    """Groq is OpenAI-compatible — reuses OpenAI provider with different base_url."""

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        api_key: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        thinking: bool = False,
    ):
        super().__init__(
            model=model,
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking=thinking,
            base_url="https://api.groq.com/openai",
        )


__all__ = ["Groq", "OpenAIResponse"]
