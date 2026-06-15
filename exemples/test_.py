import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from Pyram.llm import (
    DeepSeek,
    Cohere,
    Gemini,
    Groq,
    ToolResult,
)

load_dotenv()

# --- DeepSeek ---
client = DeepSeek(
    model="deepseek-v4-flash",
    api_key=os.getenv("dpsk"),
    temperature=0.7,
    max_tokens=200,
    thinking=False,
)

response = client.completetion("Olá, tudo bem?")
print("=== DeepSeek text ===")
print(response.text())
print()

# --- DeepSeek com thinking ---
client2 = DeepSeek(
    model="deepseek-v4-flash",
    api_key=os.getenv("dpsk"),
    temperature=0.7,
    max_tokens=200,
    thinking=True,
)

response = client2.completetion("Explique o que é Pyram framework")
print("=== DeepSeek com thinking ===")
print(response.text())
print()

# --- DeepSeek com tool calling ---
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Obtém a temperatura atual de uma cidade",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Nome da cidade",
                    }
                },
                "required": ["city"],
            },
        },
    }
]

response = client.completetion(
    "Qual a temperatura em São Paulo agora?",
    tools=tools,
    tool_choice="auto",
)

print("=== DeepSeek tool calling ===")
if response.tool_calls:
    tc = response.tool_calls[0]
    print(f"tool: {tc.name}")
    print(f"args: {tc.arguments}")

    tool_result = ToolResult(
        tool_call_id=tc.id,
        name=tc.name,
        content='{"temperature": 28, "condition": "ensolarado"}',
    )

    response2 = client.completetion(
        messages=[
            {"role": "user", "content": "Qual a temperatura em São Paulo agora?"},
            tc.to_openai_message(),
            tool_result.to_openai_message(),
        ],
        tools=tools,
    )
    print("resposta:", response2.text())
else:
    print(response.text())
print()

# --- Groq ---
groq_key = os.getenv("groq")
if groq_key:
    groq = Groq(
        model="llama-3.3-70b-versatile",
        api_key=groq_key,
        temperature=0.7,
        max_tokens=200,
    )
    resp = groq.completetion("Fale sobre Python em 1 linha")
    print("=== Groq ===")
    print(resp.text())
    print()

# --- Cohere ---
cohere_key = os.getenv("cohere")
if cohere_key:
    cohere = Cohere(
        model="command-a",
        api_key=cohere_key,
        temperature=0.3,
        max_tokens=200,
    )
    resp = cohere.completetion("Fale sobre Python em 1 linha")
    print("=== Cohere ===")
    print(resp.text())
    print()

# --- Gemini ---
gemini_key = os.getenv("gemini")
if gemini_key:
    gemini = Gemini(
        model="gemini-3.5-flash",
        api_key=gemini_key,
        temperature=0.7,
        max_tokens=200,
    )
    resp = gemini.completetion("Fale sobre Python em 1 linha")
    print("=== Gemini ===")
    print(resp.text())
    print()
