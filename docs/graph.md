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
| **`state`** | Estado da execução corrente via `contextvars`. Isolado por thread. |
| **`Flow.run()`** | Executa o DAG e devolve o `State` final |
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
| `state.chave` / `state["chave"]` | Lê (levanta `AttributeError`/`KeyError` se ausente) |
| `state.get("chave", default)` | Lê com fallback |
| `state.nested["k"] = v` | Escreve em dict aninhado (inclusive se estiver vazio) |
| `del state.chave` | Remove |
| `"chave" in state` | Verifica |
| `resultado.to_dict()` | Converte para dict |
| `resultado.copy()` | Deep copy |

Cada `run()` cria um state novo e o devolve. Ao terminar, o `state` global é
restaurado — nada vaza de uma execução para a próxima. Use sempre o retorno:

```python
resultado = pipeline.run()
print(resultado.valor)
```

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
| `retry` | `0` | Tentativas extras com backoff exponencial (1s, 2s, 4s…) |
| `timeout` | `0` | Timeout em segundos (0 = sem timeout) |

**Timeout:** a task roda em uma thread própria sobre um snapshot isolado do
state. Ao estourar, o flow levanta `FlowTimeoutError` imediatamente e as
escritas parciais daquela tentativa são descartadas — a thread é abandonada
(Python não permite matá-la), então efeitos externos da task ainda podem
acontecer. Sem `timeout`, a task roda inline, sem thread e sem cópia do state.

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

Condições são avaliadas contra o state + os globals do módulo do flow.
`state.chave` e `state["chave"]` funcionam, e `state.get(...)` também.
Se a condição não puder ser avaliada — chave ausente, nome indefinido, erro de
tipo — o flow levanta `FlowConditionError` em vez de seguir em silêncio para o
`else`. Cadeias `if/elif/else` executam exatamente um ramo.

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

Chamadas consecutivas no corpo do flow são **encadeadas**: executam na ordem
escrita, de forma determinística. Paralelismo é explícito:

```python
from apex.graph import parallel

@flow
def busca():
    with parallel():
        buscar_web()      # cada statement é um branch
        buscar_docs()
        if state.usar_cache:   # if/while funcionam dentro do bloco
            buscar_cache()
    sintetizar()          # barreira: roda depois de todos os branches
```

Cada branch roda em thread própria com um **snapshot isolado do state**. As
escritas são aplicadas ao final, na ordem de declaração do corpo:

- chave escrita por **um** branch é aplicada normalmente;
- chave escrita por **mais de um** branch gera `UserWarning` (não há descarte
  silencioso) e o último branch vence;
- prefira **uma chave por branch** (`state.dados_web`, `state.dados_docs`) e
  consolide num nó que roda depois da barreira.

---

## Subflows

Um `@flow` pode chamar outro. O subflow recebe o **mesmo state** do flow pai —
as chaves do pai são preservadas — e aparece no DAG como nó próprio.

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

Subflows não aceitam argumentos (`validar(1)` levanta `TypeError`): passe dados
via `state`, como entre tasks.

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

## Expressões e atribuições

O corpo do flow **não é executado** como Python comum — ele é compilado em DAG.
Além de chamadas de task, viram nós executáveis na ordem do grafo:

| No corpo do flow | Vira |
|------------------|------|
| `minha_task()` | nó de task |
| `minha_task(arg, kw=v)` | nó de task, argumentos avaliados na execução |
| `x = <expr>` / `x = minha_task()` | nó executado; o valor é gravado em `state.x` |
| `print(...)`, `len(...)`, `obj.metodo()` | nó inline (roda naquele ponto do DAG) |
| `state.x = ...`, `state.x += 1`, `del state.x` | nó inline |
| `def helper(): ...` dentro do corpo | task local, resolvida pelo nome |

O `state` é o canal entre nós. Variáveis locais do corpo do flow só são
visíveis entre nós inline — tasks não as enxergam, então use `state`.

Um nome desconhecido (typo) levanta `NameError` na construção do DAG.

---

## Tratamento de erros

| Exceção | Quando |
|---------|--------|
| `FlowTaskError` | a task levantou exceção (causa original em `__cause__`) |
| `FlowTimeoutError` | a task excedeu o `timeout` (também é `TimeoutError`) |
| `FlowConditionError` | a condição de um `if`/`while` não pôde ser avaliada |

```
FlowTaskError: Task [flow.task] falhou: ValueError: mensagem
```

Erros de task são embrulhados mantendo o tipo original no texto e em
`__cause__`; retry reexecuta a task até `retry` vezes antes de propagar.

---

## Referência da API

| Símbolo | Tipo | Descrição |
|---------|------|-----------|
| `flow` | decorator | `@flow` ou `@flow(name="x")` |
| `Flow.run(state, **kwargs)` | método | Executa, retorna `State` |
| `Flow.viz(fmt, path)` | método | Visualiza DAG |
| `Flow.map()` | método | Retorna o `DAG` construído |
| `task` | decorator | `@task(retry=N, timeout=S)` |
| `state` | proxy | State implícito da execução corrente |
| `parallel` | context | `with parallel(): ...` |
| `FlowError` | exceção | Base de `FlowTaskError` e `FlowConditionError` |
| `FlowTaskError` | exceção | Task falhou |
| `FlowTimeoutError` | exceção | Task estourou o timeout |
| `FlowConditionError` | exceção | Condição de `if`/`while` inválida |
