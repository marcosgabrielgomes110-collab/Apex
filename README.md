<p align="center">
  <picture>
    <img src="images/Apex.png" alt="Apex Logo" width="180"/>
  </picture>
</p>

<h1 align="center">Apex</h1>

<p align="center">
  <strong>Motor de workflows em Python — DAG, @flow, @task, state implícito</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/version-0.1.0-blueviolet" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/tests-106%20passing-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/dependencies-zero-lightgrey" alt="Dependencies">
</p>

---

## O que é

**Apex** é um framework Python zero-dependências para construir workflows, automações e agentes. Transforma funções Python comuns em **grafos acíclicos dirigidos (DAGs)** analisando o código-fonte em tempo real.

```python
from apex.graph import flow, state

@flow
def meu_workflow():
    etapa1()
    etapa2()

meu_workflow.run(state={"chave": "valor"})
```

---

## Quick Start

```bash
pip install apex-taskflow
```

```python
from apex.graph import flow, task, state

@task(retry=2)
def buscar_dados():
    state.dados = {"valor": 42}

@task(timeout=10)
def processar():
    state.resultado = state.dados["valor"] * 2

@flow
def pipeline():
    buscar_dados()
    processar()

resultado = pipeline.run()
print(resultado.resultado)  # 84
```

---

## Filosofia

- **Zero configuração** — decorators e funções padrão
- **Implícito por design** — `state` global por execução sem injeção manual
- **Tudo é uma task** — toda chamada de função vira nó no DAG
- **Paralelismo automático** — tasks independentes rodam em paralelo
- **Visualização nativa** — ASCII, SVG, Mermaid, HTML, PNG

---

## Estrutura

```
apex/
├── __init__.py          # from apex.graph import flow, task, state
├── __version__.py       # 0.1.0
└── graph/
    ├── _state.py        # State + _StateProxy + contextvars
    ├── _dag.py          # AST walker → DAG + cycle detection
    ├── _scheduler.py    # Flow, @flow, @task, executor, retry, timeout
    └── _viz.py          # ASCII, SVG, Mermaid, HTML, PNG
```

---

## Documentação

| Seção | Conteúdo |
|-------|----------|
| [graph — motor de workflows](docs/graph.md) | `@flow`, `@task`, `state`, scheduler, DAG |
| [Exemplos completos](docs/examples.md) | Pipeline, e-commerce, ReAct, padrões |

---

## Licença

MIT — veja [LICENSE](LICENSE).
