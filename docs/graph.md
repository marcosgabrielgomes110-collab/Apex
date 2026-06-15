<p align="center">
  <picture>
    <img src="../images/PyramLogo.png" alt="Pyram Logo" width="120"/>
  </picture>
  <br>
  <strong>Pyram.graph</strong> — Motor de Workflows: DAG, AST, @flow, @task
</p>

---

## 📋 Conceitos

| Conceito | O que é |
|----------|---------|
| **`@flow`** | Decorator que transforma uma função em workflow com detecção automática de DAG |
| **`@task`** | Configura metadados de execução (retry, timeout, checkpoint, cache) |
| **`state`** | State implícito via `contextvars` — acesse de qualquer função |
| **`Flow.run()`** | Executa o DAG com checkpoint, cache e paralelismo |
| **`Flow.viz()`** | Visualização ASCII do DAG |
| **`Flow.viz_svg()`** | Exporta SVG do DAG |
| **`parallel()`** | Context manager para paralelismo explícito |

---

## 🎬 `@flow`

```python
from Pyram.graph import flow, state

# Cada chamada de função vira um nó no DAG
@flow
def chatbot():
    classificar()     # nó 1
    buscar_dados()    # nó 2
    responder()       # nó 3

# Executa o workflow
resultado = chatbot.run(state={"input": "quero um notebook"})
print(resultado.to_dict())

# Visualiza o DAG
print(chatbot.viz())
# classificar
# ├── buscar_dados
# │   └── responder
```

---

## 🧠 `state` implícito

O state é **global por execução** — acesse e modifique de qualquer lugar:

```python
from Pyram.graph import flow, state

def etapa1():
    state.nome = "Pyram"
    state.valor = 42

def etapa2():
    print(state.nome, state.valor)     # Pyram 42
    state.nested = {"chave": "valor"}  # auto-cria dicts aninhados

@flow
def demo():
    etapa1()
    etapa2()

result = demo.run()
print(result.nested)   # {'chave': 'valor'}
```

> O state usa `contextvars.ContextVar` — cada chamada de `flow.run()` tem seu state isolado. Thread-safe.

### Métodos do State

```python
result.to_dict()        # → dict puro
result.copy()           # → deep copy
"key" in result         # → True/False
bool(result)            # → True se não vazio
len(result)             # → número de chaves
```

---

## ⚙️ `@task` — Configuração

```python
from Pyram.graph import task

@task(retry=3)                     # 3 tentativas com backoff exponencial
def operacao_instavel():
    import random
    if random.random() < 0.5:
        raise RuntimeError("falha")
    state.ok = True

@task(timeout=30)                  # timeout de 30s
@task(checkpoint=True)             # salva checkpoint após execução
@task(cache=True)                  # cache por hash dos argumentos

@task(retry=3, timeout=10, checkpoint=True, cache=True)
def pagamento():
    state.status = processar_pagamento(state.order)
```

### Parâmetros

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `retry` | `0` | Número de tentativas extras (backoff exponencial 2^n) |
| `timeout` | `0` | Timeout em segundos (0 = sem timeout) |
| `checkpoint` | `False` | Salva state após execução (permite recovery) |
| `cache` | `False` | Cache por hash de args (pula re-execução) |

---

## 🔀 Condicionais

`if/else` são detectados automaticamente pelo AST e viram nós condicionais:

```python
@flow
def roteador():
    classificar()
    if state.intent == "compra":
        produtos()
    else:
        suporte()
    finalizar()  # nó merge implícito

print(roteador.viz())
# classificar
# └── ? state.intent == 'compra'
#     ├── produtos
#     │   └── merge
#     └── suporte
#         └── [merge...]
```

> O ramo não executado é **bloqueado** (não executa). O merge implícito garante que o fluxo se reúna.

---

## 🔄 Loops

```python
@flow
def agente():
    while not state.finished:
        pensar()
        agir()

result = agente.run(state={"finished": False, "count": 0})
# pensar → agir → pensar → agir → ... até state.finished = True

print(agente.viz())
# ↻ not state.finished
# └── pensar
#     └── agir
```

> Limite de segurança: 100 iterações. Back-edge é automaticamente detectada e ignorada no topological sort.

---

## ⚡ Paralelismo

### Implícito (fork automático)

Tarefas consecutivas que **não dependem umas das outras** executam em paralelo:

```python
@flow
def pedido():
    verificar_pagamento()   # ← roda em paralelo
    verificar_estoque()     # ← roda em paralelo
    faturar()               # ← só executa após ambas

print(pedido.viz())
# verificar_pagamento
# └── verificar_estoque
#     └── faturar
```

### Explícito com `with parallel()`

```python
from Pyram.graph import parallel

@flow
def busca_completa():
    with parallel():
        buscar_web()
        buscar_docs()
        buscar_db()
    sintetizar()
```

---

## 🧪 Checkpoint & Recovery

```python
@task(checkpoint=True)
def etapa_critica():
    state.dado = operacao_perigosa()

@flow
def pipeline():
    preparar()
    etapa_critica()   # ← salva checkpoint
    finalizar()

# Se falhar na 2ª execução, retoma de etapa_critica
pipeline.run(state={"progresso": 0})
```

Os checkpoints ficam em `.PyramCache/graph/{flow_name}/checkpoints/`.

---

## 🎨 Visualização

```python
# ASCII
print(chatbot.viz())
# classificar
# └── ? state.intent == 'compra'
#     ├── produtos
#     └── suporte

# SVG
chatbot.viz_svg("workflow.svg")
```

---

## 🧠 Exemplo: Agente ReAct

```python
from Pyram.graph import flow, task, state

@task(retry=2)
def pensar():
    """LLM decide o que fazer"""
    state.thought = llm(f"Contexto: {state.input}")
    state.action = extrair_acao(state.thought)

@task(retry=2, cache=True)
def agir():
    """Executa a ação decidida"""
    state.result = executar_acao(state.action)

@flow
def react_agent():
    while not state.concluido:
        pensar()
        if "final_answer" in state.action:
            state.concluido = True
        else:
            agir()

resultado = react_agent.run(state={
    "input": "Quanto é 25 * 4 + 10?",
    "concluido": False,
})
```

---

## 💾 Cache de tasks

```python
@task(cache=True)
def consulta_api():
    state.dados = chamada_externa()

# Na segunda execução com mesmos inputs, pula a task
flow.run(state={"param": "x"})
flow.run(state={"param": "x"})  # task consulta_api → cache hit
```

O cache usa SHA256 do nome da task + estado atual, armazenado em `.PyramCache/graph/{flow_name}/cache/`.
