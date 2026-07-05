<p align="center">
  <picture>
    <img src="../images/Apex.png" alt="Apex Logo" width="100"/>
  </picture>
  <br>
  <strong>apex.graph</strong> — Motor de Workflows
</p>

---

> `apex.graph` é o núcleo do Apex. Transforma funções Python em DAGs via análise de AST e executa tasks com retry, timeout e paralelismo.

---

## Índice

- [Conceitos](#conceitos)
- [`@flow` — o workflow](#flow--o-workflow)
- [`state` — estado implícito](#state--estado-implícito)
- [`@task` — configuração de execução](#task--configuração-de-execução)
- [Condicionais (if/else)](#condicionais-ifelse)
- [Loops (while)](#loops-while)
- [Paralelismo](#paralelismo)
- [Subflows](#subflows)
- [Visualização](#visualização)
- [Tratamento de erros](#tratamento-de-erros)
- [Referência da API](#referência-da-api)

---

## Conceitos

| Conceito | Descrição |
|----------|-----------|
| **`@flow`** | Decorator que analisa o AST e constrói um DAG automaticamente |
| **`@task`** | Configura `retry` e `timeout` em tasks |
| **`state`** | Estado global implícito via `contextvars`. Thread-safe. |
| **`Flow.run()`** | Executa o DAG com paralelismo |
| **`Flow.viz()`** | Visualiza em ASCII, SVG, Mermaid, HTML ou PNG |
| **`parallel()`** | Context manager para paralelismo explícito |

---

## `@flow` — o workflow

```python
from apex.graph import flow, state

def classificar():
    state.intencao = "compra"

def buscar():
    state.resultados = ["item A", "item B"]

@flow
def chatbot():
    classificar()
    buscar()

chatbot.run()
print(chatbot.viz())
```

### `Flow.run(state, **kwargs)`

```python
# Via dict
meu_flow.run(state={"inicial": "valor"})

# Via kwargs (injetados no state)
meu_flow.run(inicial="valor", debug=True)
```

---

## `state` — estado implícito

```python
from apex.graph import flow, state

def etapa1():
    state.nome = "Apex"
    state.valor = 42

def etapa2():
    state.valor *= 2

@flow
def pipeline():
    etapa1()
    etapa2()

resultado = pipeline.run()
print(resultado.valor)  # 84
```

| Operação | Comportamento |
|----------|---------------|
| `state.chave = valor` | Escreve |
| `state.chave` | Lê (levanta `AttributeError` se ausente) |
| `del state.chave` | Remove |
| `"chave" in state` | Verifica |
| `resultado.to_dict()` | Converte para dict |
| `resultado.copy()` | Deep copy |

---

## `@task` — configuração

```python
from apex.graph import task

@task(retry=3)
def instavel():
    if random.random() < 0.5:
        raise RuntimeError("falha")
    state.ok = True

@task(timeout=30)
def lenta():
    time.sleep(10)
```

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `retry` | `0` | Tentativas extras com backoff exponencial |
| `timeout` | `0` | Timeout em segundos (0 = sem timeout) |

O valor de retorno da task é mergido no state como `state.nome_da_task`:

```python
@task()
def calcular():
    return 42

# resultado.calcular == 42
```

---

## Condicionais (if/else)

```python
@flow
def roteador():
    classificar()
    if state.intencao == "compra":
        produtos()
    else:
        suporte()
```

```
classificar
└── ? state.intencao == 'compra'
    ├── produtos
    │   └── merge
    └── suporte
        └── [merge...]
```

---

## Loops (while)

```python
@flow
def agente():
    while not state.finalizado:
        pensar()
        agir()
```

Limite de segurança: **100 iterações**.

---

## Paralelismo

Tasks consecutivas sem dependência rodam em paralelo automaticamente:

```python
@flow
def pedido():
    verificar_pagamento()     # ← paralelo
    verificar_estoque()       # ← paralelo
    faturar()                 # ← aguarda ambos
```

Explícito com `with parallel()`:

```python
from apex.graph import parallel

@flow
def busca():
    with parallel():
        buscar_web()
        buscar_docs()
    sintetizar()
```

---

## Subflows

```python
@flow
def validar():
    state.pagamento_ok = True

@flow
def processar():
    validar()
    if state.pagamento_ok:
        state.status = "aprovado"
```

---

## Visualização

**5 formatos:**

```python
flow.viz()                    # ASCII (padrão)
flow.viz("svg", path="f.svg") # SVG
flow.viz("mermaid")           # Mermaid (Markdown)
flow.viz("html", path="f.html") # HTML interativo
flow.viz("png", path="f.png")   # PNG (requer cairosvg)
```

---

## Tratamento de erros

```
RuntimeError: Task [flow.task] falhou: ValueError: mensagem
```

Debug de condições: `export APEX_DEBUG=1`

---

## Referência da API

| Símbolo | Tipo | Descrição |
|---------|------|-----------|
| `flow` | decorator | `@flow` ou `@flow(name="x")` |
| `Flow.run(state, **kwargs)` | método | Executa, retorna `State` |
| `Flow.viz(fmt, path)` | método | Visualiza DAG |
| `task` | decorator | `@task(retry=N, timeout=S)` |
| `state` | proxy | State global implícito |
| `parallel` | context | `with parallel(): ...` |
