<p align="center">
  <picture>
    <img src="../images/PyramLogo.png" alt="Pyram Logo" width="120"/>
  </picture>
  <br>
  <strong>Pyram.llm</strong> — Provedores LLM com interface unificada
</p>

---

## 📋 Overview

Todos os provedores compartilham **a mesma interface**:

```python
resposta = provedor.completetion(
    prompt="string",           # mensagem do usuário
    system="system prompt",    # instrução de sistema
    tools=[...],               # schemas de ferramentas (opcional)
    tool_choice="auto",        # "auto" | "any" | "none" | {"function": {"name": "..."}}
    messages=[...],            # histórico completo (opcional)
)
# → CompletionResponse (.text(), .jsn(), .content, .tool_calls, .thinking)
```

### CompletionResponse

| Método/Atributo | Retorno | Descrição |
|------------------|---------|-----------|
| `.text()` | `str` | Conteúdo formatado (thinking + resposta) |
| `.jsn()` | `dict` | Resposta raw da API |
| `.content` | `str` | Apenas o texto da resposta |
| `.tool_calls` | `list[ToolCall]` | Chamadas de ferramentas |
| `.thinking` | `str` | Raciocínio interno (se disponível) |

---

## 🧠 DeepSeek

```python
from Pyram.llm import DeepSeek

ia = DeepSeek(
    model="deepseek-v4-flash",    # modelo
    api_key="sk-...",             # API key
    max_tokens=2000,              # max tokens
    temperature=0.7,              # temperatura (0.0 - 1.0)
    thinking=True,                # ativa reasoning_content
    use_cache=False,              # cache em .PyramCache/
)

resp = ia.completetion("Explique buracos negros")
print(resp.text())
# thinkink >> [raciocínio interno]
# response >> [resposta final]

ia.completetion(
    system="Você é um físico teórico",
    messages=[
        {"role": "user", "content": "O que é spacetime?"}
    ]
)
```

<details>
<summary><strong>🔧 Detalhes Técnicos</strong></summary>

- **Endpoint:** `POST https://api.deepseek.com/chat/completions`
- **Tool Calling:** OpenAI-compatible (`tools` + `tool_choice`)
- **Thinking:** Envia `thinking: {type: "enabled"}` → recebe `reasoning_content`
- **Cache:** `ResponseCache` com hash SHA256 do payload completo
</details>

---

## 🟢 OpenAI

```python
from Pyram.llm import OpenAI

ia = OpenAI(
    model="gpt-4o",
    api_key="sk-...",
    base_url="https://api.openai.com",  # custom endpoint
)

resp = ia.completetion("Criativo: escreva um haiku")
print(resp.text())
# response >> [haiku]
```

<details>
<summary><strong>🔧 Detalhes Técnicos</strong></summary>

- **Endpoint:** `POST {base_url}/v1/chat/completions`
- **Tool Calling:** Nativo OpenAI
- **Custom base_url:** Útil para proxies ou APIs compatíveis
</details>

---

## 🟣 Anthropic

```python
from Pyram.llm import Anthropic

ia = Anthropic(
    model="claude-sonnet-4-6",
    api_key="sk-ant-...",
    thinking=True,           # ativa extended thinking
)

resp = ia.completetion("Analise este código:")
```

<details>
<summary><strong>🔧 Detalhes Técnicos</strong></summary>

- **Endpoint:** `POST https://api.anthropic.com/v1/messages`
- **Headers:** `x-api-key`, `anthropic-version: 2023-06-01`
- **Tool Calling:** Formato nativo Anthropic com `name`/`description`/`input_schema`
- **Conversão:** Mensagens são convertidas via `_convert_messages_anthropic()`
- **Tool choice:** `auto` → `{type: "auto"}`, `any` → `{type: "any"}`, `none` → `{type: "none"}`
</details>

---

## 🔵 Gemini

```python
from Pyram.llm import Gemini

ia = Gemini(
    model="gemini-3.5-flash",
    api_key="AIza...",
)

resp = ia.completetion("Explique em 1 parágrafo")
```

<details>
<summary><strong>🔧 Detalhes Técnicos</strong></summary>

- **Endpoint:** `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
- **Headers:** `x-goog-api-key`
- **Tool Calling:** `functionDeclarations` → `functionCall` → `functionResponse`
- **Formato:** Usa `contents`/`parts` em vez de `messages`
- **Tool choice:** Mapeado para `functionCallingConfig.mode`
</details>

---

## 🟠 Cohere

```python
from Pyram.llm import Cohere

ia = Cohere(
    model="command-nightly",
    api_key="...",
    temperature=0.3,
)

resp = ia.completetion("Resuma este artigo:")
```

<details>
<summary><strong>🔧 Detalhes Técnicos</strong></summary>

- **Endpoint:** `POST https://api.cohere.com/v2/chat`
- **Formato v2:** `messages` array com role/tool_calls (não string content)
- **Tool Calling:** OpenAI-compatible com conversão
- **Tool choice:** `auto`/`none`/`REQUIRED` string
</details>

---

## 🟡 Groq

```python
from Pyram.llm import Groq

ia = Groq(
    model="llama-3.3-70b-versatile",
    api_key="gsk-...",
)

resp = ia.completetion("Traduza para português")
```

<details>
<summary><strong>🔧 Detalhes Técnicos</strong></summary>

- **Extends:** `OpenAI` com `base_url="https://api.groq.com/openai"`
- **API 100% compatível** com OpenAI
- **Tool Calling:** Mesmo formato OpenAI
</details>

---

## 🌊 Streaming

Todos os provedores suportam streaming com `stream=True`. O método retorna um `Generator[StreamChunk]`:

```python
from Pyram.llm import DeepSeek, StreamChunk

ia = DeepSeek(api_key="sk-...")

stream = ia.completetion("Conte uma história curta", stream=True)

for chunk in stream:
    if chunk.content:
        print(chunk.content, end="", flush=True)
    if chunk.thinking:
        print(f"[pensando: {chunk.thinking}]")
    if chunk.tool_calls:
        for tc in chunk.tool_calls:
            print(f"[tool: {tc.name}({tc.arguments})]")
    if chunk.done:
        print(f"\n[finalizado: {chunk.finish_reason}]")
```

### StreamChunk

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `.content` | `str` | Texto gerado incrementalmente |
| `.thinking` | `str` | Raciocínio interno (se disponível) |
| `.tool_calls` | `list[ToolCall] \| None` | Chamadas de ferramentas completas (no fim do stream) |
| `.done` | `bool` | `True` quando a resposta terminou |
| `.finish_reason` | `str \| None` | Motivo da finalização (`stop`, `length`, `tool_use`, etc.) |

> **Nota:** Tool calls em streaming chegam no último chunk (quando `done=True`). O conteúdo de texto e ferramentas nunca aparecem no mesmo chunk.

---

## 🔄 Tool Calling com LLM

```python
from Pyram.llm import DeepSeek
from Pyram.tools import tool, sch, exec

@tool(info="Calcula preço com desconto")
def calcular_preco(valor: float, desconto: float = 0) -> float:
    return valor * (1 - desconto)

ia = DeepSeek(api_key="sk-...")

# 1. Envia com schemas
resp = ia.completetion(
    "Quanto fica R$ 200 com 15% de desconto?",
    tools=sch(),                     # ← schema gerado automaticamente
    tool_choice="auto",
)

# 2. Executa as ferramentas
resultados = exec(resp, use_cache=True)
for r in resultados:
    print(f"{r['name']}: {r['content']}")

# 3. Continua a conversa com resultados
resp2 = ia.completetion(messages=[
    {"role": "user", "content": "Quanto fica R$ 200 com 15% de desconto?"},
    {"role": "assistant", "tool_calls": [tc.to_openai_message() for tc in resp.tool_calls]},
    {"role": "tool", "tool_call_id": r["tool_call_id"], "content": r["content"]},
    {"role": "user", "content": "E com 20%?"},
], tools=sch())
```

---

## 📦 ToolCall & ToolResult

```python
from Pyram.llm import ToolCall, ToolResult

# Criar manualmente
tc = ToolCall(id="call_1", name="get_stock", arguments='{"sku": "123"}')

# Converter para formatos
tc.to_openai_message()        # → OpenAI message format
tc.to_anthropic_content_block()  # → Anthropic content block
tc.to_gemini_content()        # → Gemini content format

# Resultado
tr = ToolResult(tool_call_id="call_1", name="get_stock", content='{"qty": 5}')
tr.to_anthropic_content_block()  # → {"type": "tool_result", ...}
```

---

## 💾 ResponseCache

```python
from Pyram.llm import ResponseCache

cache = ResponseCache("deepseek", ttl=3600)
cache.set(payload, response_dict)
hit = cache.get(payload)  # → dict or None
cache.clear()
```
