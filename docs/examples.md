<p align="center">
  <picture>
    <img src="../images/PyramLogo.png" alt="Pyram Logo" width="120"/>
  </picture>
  <br>
  <strong>Pyram Examples</strong> — Padrões e receitas completas
</p>

---

## 📋 Sumário

| # | Exemplo | Módulos | Técnicas |
|---|---------|---------|----------|
| 1 | [Claude Code Style Agent](#1-agent-style-claude-code) | `llm`, `tools` | Tool calling, loop de execução |
| 2 | [Auto-Correção de Código](#2-auto-correção-de-código) | `llm`, `tools` | Multiple tools, reflexão |
| 3 | [Workflow E-commerce](#3-workflow-e-commerce) | `graph`, `llm` | @task retry, condicional, DAG |
| 4 | [Agente Perplexity Style](#4-agente-perplexity-style) | `llm`, `tools` | Search simulation, chain-of-thought |

---

## 1. Agent Style Claude Code

Um agente que raciocina, decide ferramentas e executa em loop até ter a resposta completa.

```python
"""Agente estilo Claude Code — pensa, age, observa, repete."""
from Pyram.llm import DeepSeek
from Pyram.tools import tool, sch, exec
import json

# ── Ferramentas ────────────────────────────────────────

@tool(info="Read the contents of a file")
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

@tool(info="List files in a directory")
def list_dir(path: str = ".") -> list:
    import os
    return os.listdir(path)

@tool(info="Write content to a file (overwrites)")
def write_file(path: str, content: str) -> str:
    with open(path, "w") as f:
        f.write(content)
    return f"Written {len(content)} bytes to {path}"

@tool(info="Run a shell command and get output")
def run_command(cmd: str) -> str:
    import subprocess
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return result.stdout + result.stderr

# ── Agente ─────────────────────────────────────────────

SYSTEM = """You are an AI assistant with tool access.
For each user request, think step by step.
Use tools when needed. When you have the final answer, call finish()."""

@tool(info="Call when you have the complete final answer")
def finish(answer: str) -> str:
    return f"✅ DONE: {answer}"

class Agent:
    def __init__(self, api_key: str):
        self.llm = DeepSeek(api_key=api_key, model="deepseek-chat", max_tokens=4000)
        self.messages = [{"role": "system", "content": SYSTEM}]

    def run(self, task: str) -> str:
        self.messages.append({"role": "user", "content": task})
        max_steps = 10

        for step in range(max_steps):
            print(f"\n{'='*40}\nStep {step + 1}")
            resp = self.llm.completetion(messages=self.messages, tools=sch(), tool_choice="auto")

            if resp.tool_calls:
                print(f"🛠 Tools: {[tc.name for tc in resp.tool_calls]}")
                results = exec(resp)
                for r in results:
                    if r["name"] == "finish":
                        return json.loads(r["content"]).get("answer", r["content"])
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": r["tool_call_id"],
                        "content": r["content"],
                    })
            else:
                print(f"💬 {resp.content[:200]}...")
                self.messages.append({"role": "assistant", "content": resp.content})

        return "Max steps reached."

# ── Uso ────────────────────────────────────────────────

agent = Agent(api_key="sk-...")
result = agent.run("Read the file 'main.py' and tell me what it does")
print(f"\n🎯 Result: {result}")
```

---

## 2. Auto-Correção de Código

Um agente que escreve código, testa e corrige automaticamente.

```python
"""Agente que escreve, testa e corrige código em loop."""
from Pyram.llm import DeepSeek
from Pyram.tools import tool, sch, exec
import json

@tool(info="Write Python code to a file")
def write_code(filename: str, code: str) -> str:
    with open(filename, "w") as f:
        f.write(code)
    return f"✅ Written to {filename}"

@tool(info="Run Python tests and return output")
def run_tests(filename: str) -> str:
    import subprocess
    result = subprocess.run(
        ["python", filename],
        capture_output=True, text=True, timeout=15
    )
    return result.stdout + result.stderr

@tool(info="Final answer with the corrected code")
def final_answer(code: str, explanation: str) -> str:
    return json.dumps({"code": code, "explanation": explanation})

SYSTEM = """You are a coding agent. Write code → test → fix → repeat until tests pass.
When all tests pass, call final_answer()."""

class CodingAgent:
    def __init__(self, api_key: str):
        self.llm = DeepSeek(api_key=api_key, max_tokens=4000, thinking=True)
        self.messages = [{"role": "system", "content": SYSTEM}]

    def run(self, task: str, max_iterations: int = 5):
        self.messages.append({"role": "user", "content": task})

        for i in range(max_iterations):
            resp = self.llm.completetion(messages=self.messages, tools=sch(), tool_choice="auto")

            if resp.tool_calls:
                results = exec(resp)
                for r in results:
                    if r["name"] == "final_answer":
                        data = json.loads(r["content"])
                        print(f"\n🎯 {data['explanation']}")
                        print(f"📄 Code:\n{data['code']}")
                        return data["code"]

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": r["tool_call_id"],
                        "content": r["content"],
                    })
            else:
                self.messages.append({"role": "assistant", "content": resp.content})

        return "Max iterations."

agent = CodingAgent(api_key="sk-...")
agent.run("Write a fibonacci function and test it")
```

---

## 3. Workflow E-commerce

```python
"""Workflow de e-commerce com checkout, pagamento e estoque."""
from Pyram.graph import flow, task, state, parallel

@task(retry=2)
def validar_carrinho():
    if not state.carrinho.get("itens"):
        raise ValueError("Carrinho vazio")
    state.subtotal = sum(i["preco"] for i in state.carrinho["itens"])
    print(f"✅ Carrinho validado: R$ {state.subtotal:.2f}")

@task(retry=3, checkpoint=True)
def processar_pagamento():
    print(f"💳 Pagamento de R$ {state.subtotal:.2f}...")
    state.pagamento_id = "PAY-123"
    state.pago = True

@task(retry=2)
def verificar_estoque():
    state.estoque_ok = all(i["qtd"] <= 10 for i in state.carrinho["itens"])
    print(f"📦 Estoque: {'OK' if state.estoque_ok else 'BAIXO'}")

@task(retry=3)
def gerar_nota_fiscal():
    state.nf_id = f"NF-{hash(state.pagamento_id) % 10000}"
    print(f"📄 Nota fiscal: {state.nf_id}")

@task()
def enviar_confirmacao():
    print(f"📧 Email de confirmação para {state.cliente_email}")
    state.enviado = True

@flow
def checkout():
    validar_carrinho()
    # Pagamento + estoque rodam em paralelo (fork implícito)
    processar_pagamento()
    verificar_estoque()
    # Só continua se ambos OK
    if state.pago and state.estoque_ok:
        gerar_nota_fiscal()
        enviar_confirmacao()
    else:
        state.erro = "Pagamento ou estoque falhou"

resultado = checkout.run(state={
    "cliente_email": "cliente@email.com",
    "carrinho": {
        "itens": [
            {"nome": "Notebook", "preco": 4500, "qtd": 1},
            {"nome": "Mouse", "preco": 150, "qtd": 2},
        ]
    },
})

print(f"\n🎯 Resultado: NF={resultado.nf_id}, Enviado={resultado.enviado}")
print(checkout.viz())
```

---

## 4. Agente Perplexity Style

```python
"""Agente que pesquisa, lê e sintetiza respostas com fontes."""
from Pyram.llm import DeepSeek
from Pyram.tools import tool, sch, exec
from Pyram.graph import flow, state, task

# ── Ferramentas de pesquisa simuladas ───────────────────

@tool(info="Search the web for a query, returns top results")
def search_web(query: str, num_results: int = 5) -> list[dict]:
    simulated = {
        "preço bitcoin": [
            {"title": "Bitcoin hoje", "snippet": "BTC está em R$ 350.000", "url": "ex.com/btc"},
            {"title": "Cotação Bitcoin", "snippet": "Bitcoin valoriza 5% no mês", "url": "ex.com/cot"},
        ],
        "python async": [
            {"title": "Async Python Guide", "snippet": "asyncio é o módulo padrão", "url": "ex.com/async"},
        ],
    }
    return simulated.get(query.lower(), [
        {"title": "Resultado", "snippet": f"Informações sobre {query}", "url": f"ex.com/{query}"}
    ])

@tool(info="Read and summarize a URL")
def read_url(url: str) -> str:
    return f"Conteúdo simulado de {url}: informações relevantes para a pergunta."

@tool(info="Present the final answer with sources")
def final_answer(answer: str, sources: list[str]) -> str:
    srcs = "\n".join(f"  📚 {s}" for s in sources)
    return f"{answer}\n\n**Fontes:**\n{srcs}"

# ── Workflow ───────────────────────────────────────────

@task(cache=True)
def pesquisar():
    """Fase de pesquisa — busca informações"""
    query = state.pergunta
    state.resultados_busca = search_web(query)

@task
def analisar():
    """Fase de análise — lê e extrai informações"""
    state.informacoes = []
    for r in state.resultados_busca:
        state.informacoes.append(read_url(r["url"]))

@task
def sintetizar():
    """Fase de síntese — gera resposta final com LLM"""
    contexto = "\n".join(state.informacoes)
    state.resposta_bruta = llm.synthesize(state.pergunta, contexto)

@flow
def perplexity_agent():
    pesquisar()
    analisar()
    sintetizar()

# Execução
SYSTEM_PROMPT = """You are a research assistant.
Synthesize the provided information into a clear answer with sources."""

llm = DeepSeek(api_key="sk-...", system=SYSTEM_PROMPT)

resultado = perplexity_agent.run(state={
    "pergunta": "Qual o preço atual do Bitcoin?",
})
print(f"\n📝 Resposta:\n{resultado.resposta_bruta}")
print(perplexity_agent.viz())
```

---

## 📦 Padrões & Técnicas

### Loop de Agente (Tool Calling Loop)

```
→ User: pergunta
→ LLM: decide se usa tool ou responde
→ Se tool: exec → resultado → volta pro LLM
→ Se resposta: finaliza
```

### Workflow com Checkpoint

```
→ @task(checkpoint=True) em operações críticas
→ Se workflow falhar, retoma do último checkpoint
→ Checkpoints em .PyramCache/graph/{flow}/checkpoints/
```

### Cache Inteligente

```
→ LLM: ResponseCache com TTL (evita re-chamar API)
→ Tools: exec(use_cache=True) (evita re-executar)
→ Graph: @task(cache=True) (evita re-processar)
```

### Condicionais + Loops

```
→ if/else vira diamond no DAG com merge implícito
→ while vira back-edge no DAG
→ state.finished controla saída de loop
```
