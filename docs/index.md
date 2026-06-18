<p align="center">
  <picture>
    <img src="../images/Apex.png" alt="Apex Logo" width="140"/>
  </picture>
  <br>
  <strong>Apex</strong> — Documentação
</p>

---

> Apex é um framework Python zero-dependências para construir workflows, automações e agentes.
>
> ⚡ **Código Python comum → AST → DAG → Execução**

---

## Comece por aqui

| Se você quer | Vá para |
|--------------|---------|
| Instalar e rodar o primeiro workflow | [README → Quick Start](../README.md#quick-start) |
| Entender `@flow`, `@task` e `state` | [graph — motor de workflows](graph.md) |
| Ver exemplos completos | [Examples](examples.md) |

---

## Resumo da API

```python
from apex.graph import flow, task, state, parallel

@task(retry=2, timeout=10)
def minha_task():
    state.resultado = executar()

@flow
def meu_workflow():
    minha_task()
    if state.resultado:
        finalizar()

resultado = meu_workflow.run(parametro="valor")
print(meu_workflow.viz("mermaid"))
meu_workflow.viz_svg("workflow.svg")
```

---

## Por que Apex?

| Problema | Solução Apex |
|----------|-------------|
| Workflows em YAML/JSON são verbosos | Código Python puro — sem config files |
| Frameworks pesados para tarefas simples | Zero dependências, instalação instantânea |
| State management manual propenso a erros | State implícito via contextvars — thread-safe |
| Visualização complexa de pipelines | 5 formatos de saída com uma linha de código |

---

## Projeto

| Item | Valor |
|------|-------|
| Versão | **0.1.0** |
| Licença | MIT |
| Python | 3.11+ |
| Dependências | **zero** |
| Testes | **106** (pytest) |
| Repositório | [github.com/marcosgabrielgomes110-collab/Apex](https://github.com/marcosgabrielgomes110-collab/Apex) |
