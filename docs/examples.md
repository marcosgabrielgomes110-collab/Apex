<p align="center">
  <picture>
    <img src="../images/Apex.png" alt="Apex Logo" width="100"/>
  </picture>
  <br>
  <strong>Apex Examples</strong> — Padrões e receitas completas
</p>

---

## Índice

- [1. Pipeline linear](#1-pipeline-linear)
- [2. Workflow E-commerce](#2-workflow-e-commerce)
- [3. Agente ReAct com loop](#3-agente-react-com-loop)
- [Padrões & Técnicas](#padrões--técnicas)

---

## 1. Pipeline linear

```python
from apex.graph import flow, task, state

@task(retry=2)
def validar():
    if not state.input:
        raise ValueError("input é obrigatório")
    state.valido = True

@task(timeout=10)
def processar():
    state.resultado = state.input * 2

@flow
def pipeline():
    validar()
    processar()

resultado = pipeline.run(input=21)
print(resultado.to_dict())  # {'input': 21, 'valido': True, 'resultado': 42}
```

---

## 2. Workflow E-commerce

```python
from apex.graph import flow, task, state, parallel

@task(retry=2)
def validar_carrinho():
    state.subtotal = sum(i["preco"] * i["qtd"] for i in state.carrinho["itens"])

@task(retry=3)
def processar_pagamento():
    state.pagamento_id = "PAY-123"
    state.pago = True

@task(retry=2)
def verificar_estoque():
    state.estoque_ok = True

@task()
def gerar_nota_fiscal():
    state.nf_id = "NF-1234"

@task()
def enviar_confirmacao():
    state.enviado = True

@flow
def checkout():
    validar_carrinho()
    processar_pagamento()    # ← paralelo
    verificar_estoque()      # ← paralelo
    if state.pago and state.estoque_ok:
        gerar_nota_fiscal()
        enviar_confirmacao()

resultado = checkout.run(
    cliente_email="joao@email.com",
    carrinho={"itens": [{"nome": "Notebook", "preco": 4500, "qtd": 1}]},
)

print(checkout.viz("mermaid"))
```

---

## 3. Agente ReAct com loop

```python
from apex.graph import flow, task, state

@task(retry=2)
def pensar():
    state.pensamento = f"Analisando: {state.pergunta}"

def agir():
    if len(state.acoes) < 2:
        state.acoes.append("buscar")
    else:
        state.acao_final = f"Resposta para: {state.pergunta}"
        state.finalizado = True

@flow
def react_agent():
    while not state.finalizado:
        pensar()
        agir()

resultado = react_agent.run(
    pergunta="Capital do Brasil?",
    acoes=[],
    finalizado=False,
)
print(resultado.acao_final)
```

---

## Padrões & Técnicas

### Loop de Agente

```
→ State: pergunta
→ Enquanto não finalizado:
    → Pensar (task decide ação)
    → Agir (executa ação)
→ State: resposta
```

### Condicionais + Loops

```
→ if/else vira diamond no DAG com merge implícito
→ while vira back-edge
→ state.finalizado controla saída
```

### Paralelismo

```
→ Nós no mesmo nível do topological sort → ThreadPoolExecutor
→ with parallel(): → paralelismo explícito
```
