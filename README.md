<p align="center">
  <picture>
    <img src="images/PyramLogo.png" alt="Pyram Logo" width="180"/>
  </picture>
</p>

<h1 align="center">⚡ Pyram</h1>

<p align="center">
  <strong>Workflows & Agentes com IA</strong> — DAGs · Tools · LLMs
</p>

<p align="center">
  <a href="docs/index.md"><img src="https://img.shields.io/badge/docs-index-blue?style=flat-square" alt="Docs"></a>
  <a href="docs/llm.md"><img src="https://img.shields.io/badge/docs-LLM%20Providers-8A2BE2?style=flat-square" alt="LLM Docs"></a>
  <a href="docs/tools.md"><img src="https://img.shields.io/badge/docs-Tools-FF6B35?style=flat-square" alt="Tools Docs"></a>
  <a href="docs/graph.md"><img src="https://img.shields.io/badge/docs-Graph%20Workflows-00C853?style=flat-square" alt="Graph Docs"></a>
  <a href="docs/examples.md"><img src="https://img.shields.io/badge/docs-Examples-FF4081?style=flat-square" alt="Examples"></a>
  <br>
  <a href="https://pypi.org/project/pyram-flow/"><img src="https://img.shields.io/pypi/v/pyram-flow?style=flat-square&logo=pypi&logoColor=white&label=PyPI" alt="PyPI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT">
  <img src="https://img.shields.io/badge/dependencies-httpx%20only-orange?style=flat-square" alt="httpx only">
  <img src="https://img.shields.io/badge/status-alpha-yellow?style=flat-square" alt="Alpha">
</p>

---

<p align="center">
  Pyram unifica <strong>LLM calling</strong>, <strong>tool calling</strong> e <strong>workflows DAG</strong> em uma API minimalista.<br>
  Zero dependências além de <code>httpx</code>. Sem Pydantic. Sem frameworks. Sem classes abstratas.
</p>

---

## 🚀 Quickstart

```bash
pip install pyram-flow
```

```python
# 1. LLM em 3 linhas
from Pyram.llm import DeepSeek
ia = DeepSeek(api_key="sk-...")
print(ia.completetion("Qual a capital do Brasil?").text())

# 2. Tool calling em 5 linhas
from Pyram.tools import tool, sch, exec
@tool(info="Soma dois números")
def add(a: int, b: int) -> int:
    return a + b
resp = ia.completetion("2 + 3?", tools=sch())
print(exec(resp))

# 3. Workflow em 10 linhas
from Pyram.graph import flow, state
@flow
def chatbot():
    if state.pergunta == "preço":
        state.resposta = "R$ 199,90"
    else:
        state.resposta = "Pergunte sobre preços"
resultado = chatbot.run(state={"pergunta": "preço"})
print(resultado.resposta)
```

---

## 🧭 Guia rápido

<table>
  <tr>
    <th width="25%">Módulo</th>
    <th width="45%">O que faz</th>
    <th width="30%">Documentação</th>
  </tr>
  <tr>
    <td><code>Pyram.llm</code></td>
    <td>6 provedores LLM com interface unificada, tool calling e thinking</td>
    <td><a href="docs/llm.md"><code>📗 docs/llm.md</code></a></td>
  </tr>
  <tr>
    <td><code>Pyram.tools</code></td>
    <td>Decorator <code>@tool</code> com schema automático, cache e execução</td>
    <td><a href="docs/tools.md"><code>📗 docs/tools.md</code></a></td>
  </tr>
  <tr>
    <td><code>Pyram.graph</code></td>
    <td>Motor de workflows: <code>@flow</code>, <code>@task</code>, DAG, AST, state</td>
    <td><a href="docs/graph.md"><code>📗 docs/graph.md</code></a></td>
  </tr>
  <tr>
    <td><code>Pyram.configs</code></td>
    <td>Cache unificado, diretório <code>.PyramCache</code>, TTL</td>
    <td><a href="docs/index.md"><code>📗 docs/index.md</code></a></td>
  </tr>
</table>

---

## 🧠 Provedores LLM

| Provider | Classe | Tool Calling | Thinking | Cache |
|----------|--------|:---:|:---:|:---:|
| DeepSeek | `DeepSeek` | ✅ Nativo | ✅ | ✅ |
| OpenAI | `OpenAI` | ✅ Nativo | ✅ | ✅ |
| Anthropic | `Anthropic` | ✅ Convertido | ✅ | ✅ |
| Gemini | `Gemini` | ✅ functionDeclarations | ❌ | ✅ |
| Cohere | `Cohere` | ✅ Convertido | ✅ | ✅ |
| Groq | `Groq` (extends OpenAI) | ✅ Nativo | ❌ | ✅ |

```python
# Interface 100% idêntica entre provedores
resposta = provedor.completetion(
    prompt="...",
    system="Você é um assistente...",
    tools=sch(),           # schemas de ferramentas
    tool_choice="auto",    # "auto" | "any" | "none" | {"function": {"name": "..."}}
    messages=[...],        # histórico completo (opcional)
)
# → CompletionResponse (.text(), .jsn(), .content, .tool_calls, .thinking)
```

---

## 🔧 Ferramentas

```python
from Pyram.tools import tool, sch, sch_ant, sch_gem, exec, listar

@tool(info="Busca produtos no estoque")
def buscar_produtos(categoria: str, limite: int = 10) -> list[dict]:
    return [{"nome": "Notebook", "preco": 4500}]

sch()        # → OpenAI format  (DeepSeek, Groq)
sch_ant()    # → Anthropic format
sch_gem()    # → Gemini format
exec(resp, use_cache=True)   # executa com cache

listar()     # → ["buscar_produtos"]
```

---

## 🔄 Workflows

```python
from Pyram.graph import flow, task, state, parallel

@task(retry=3, timeout=10, checkpoint=True)
def pagamento():
    state.status = "pago"

@flow
def ecommerce():
    pagamento()
    envio()
    if state.status == "pago":
        notificar()

resultado = ecommerce.run(state={"status": ""})
print(ecommerce.viz())
# pagamento
# ├── envio
# │   └── ? state.status == 'pago'
# │       ├── notificar
# │       │   └── merge
# │       └── [notificar...]
```

---

## 📁 Cache Unificado

```
.PyramCache/
├── responses/
│   ├── deepseek/     # Cache de respostas DeepSeek
│   └── openai/       # Cache de respostas OpenAI
├── tools/            # Cache de execução de tools
└── graph/
    └── {flow_name}/
        ├── checkpoints/  # Checkpoint de tasks
        ├── cache/        # Cache de tasks
        └── manifest.json
```

```python
from Pyram.configs import Cache

cache = Cache("deepseek", ttl=3600)
cache.set({"model": "deepseek-v4"}, {"choices": [...]})
hit = cache.get({"model": "deepseek-v4"})  # → dict or None
```

> Configure o diretório via `export PYRAM_CACHE_DIR=/caminho/do/cache`

---

## 📚 Documentação

| Documento | Conteúdo |
|-----------|----------|
| [`docs/llm.md`](docs/llm.md) | API completa dos 6 provedores, exemplos, detalhes técnicos |
| [`docs/tools.md`](docs/tools.md) | Decorator `@tool`, schemas, execução, cache, utilitários |
| [`docs/graph.md`](docs/graph.md) | `@flow`, `@task`, state, condicionais, loops, checkpoint |
| [`docs/examples.md`](docs/examples.md) | 4 exemplos completos: Claude Code Agent, Auto-Correção, E-commerce, Perplexity |

---

## 📄 Licença

MIT — use, modifique, distribua livremente.

---

<p align="center">
  <sub>Feito com ☕ e Python puro · <a href="https://github.com/marcosgabrielgomes110-collab/Pyram">GitHub</a></sub>
</p>
