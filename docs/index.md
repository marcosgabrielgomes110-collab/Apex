# ⚡ Pyram Documentation

<p align="center">
  <img src="../images/PyramLogo.png" alt="Pyram Logo" width="200"/>
</p>

**Pyram** is a minimalist Python framework for building AI agents, workflows, and LLM-powered automations. Three layers, one unified API, zero bloat.

---

## 📚 Table of Contents

| Section | Description |
|---------|-------------|
| [LLM Providers](llm.md) | DeepSeek, OpenAI, Anthropic, Gemini, Cohere, Groq |
| [Tool Calling](tools.md) | `@tool` decorator, schema generation, execution |
| [Workflow Engine](graph.md) | `@flow`, `@task`, DAG detection, state management |
| [Examples](examples.md) | End-to-end patterns & recipes |

---

## 🏗 Architecture

```
Pyram/
├── __init__.py          # Package entry
├── __version__.py       # Version info
├── configs.py           # Cache & path configuration
├── llm/                 # LLM providers
│   ├── base.py          # ToolCall, ToolResult, CompletionResponse, Cache
│   ├── deepseek_.py     # DeepSeek provider
│   ├── openai_.py       # OpenAI provider
│   ├── anthropic_.py    # Anthropic provider
│   ├── gemini_.py       # Gemini provider
│   ├── cohere_.py       # Cohere provider
│   └── groq_.py         # Groq (extends OpenAI)
├── tools/               # Tool calling system
│   └── __init__.py      # @tool, sch(), exec(), cache
└── graph/               # Workflow engine
    ├── _state.py        # State, _StateProxy, contextvars
    ├── _dag.py          # AST walker, DAG builder
    ├── _scheduler.py    # Flow, @flow, @task, executor
    ├── _checkpoint.py   # Checkpoint & cache persistence
    └── _viz.py          # ASCII tree & SVG export
```

---

## 🚀 Getting Started

```bash
pip install pyram-flow
```

```python
from Pyram.llm import DeepSeek
from Pyram.tools import tool, sch, exec
from Pyram.graph import flow, state, task

# 1. LLM call
ia = DeepSeek(api_key="sk-...")
resp = ia.completetion("Hello!")
print(resp.text())

# 2. Tool calling
@tool(info="Sum two numbers")
def add(a: int, b: int) -> int:
    return a + b

resp = ia.completetion("2 + 3?", tools=sch())
print(exec(resp))

# 3. Workflow
@flow
def my_agent():
    step1()
    step2()

my_agent.run(state={"key": "value"})
print(my_agent.viz())
```

---

## ⚙️ Configuration

### Cache Directory

All cache data lives in `.PyramCache/` in the working directory. Override via env var:

```bash
export PYRAM_CACHE_DIR=/var/cache/pyram
```

### Cache API

```python
from Pyram.configs import Cache

cache = Cache("my_namespace", ttl=3600)
cache.set({"input": "data"}, {"output": "result"})
hit = cache.get({"input": "data"})  # → {"output": "result"} or None
cache.exists({"input": "data"})     # → True/False
cache.clear()                       # wipe namespace
cache.remove({"input": "data"})     # remove single entry
```

---

## 📄 License

MIT
