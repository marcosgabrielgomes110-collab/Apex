<p align="center">
  <picture>
    <img src="../images/Apex.png" alt="Apex Logo" width="100"/>
  </picture>
  <br>
  <strong>Agentes Autônomos — Padrões Avançados</strong>
</p>

---

> Exemplos de média complexidade para construir agentes de IA autônomos usando `@flow`, `@task`, loops e condicionais.

---

## Índice

- [1. Agente ReAct com ferramentas](#1-agente-react-com-ferramentas)
- [2. Agente de Pesquisa e Síntese](#2-agente-de-pesquisa-e-síntese)
- [3. Orquestrador de Subtarefas](#3-orquestrador-de-subtarefas)
- [4. Agente com Memória de Curto Prazo](#4-agente-com-memória-de-curto-prazo)

---

## 1. Agente ReAct com ferramentas

Agente que **raciocina, age e observa** em loop até completar uma tarefa. Cada ferramenta é uma `@task`.

```python
from apex.graph import flow, task, state

# ── Ferramentas (tools) ──────────────────────────────────────

@task(retry=2)
def ler_arquivo():
    """Lê o conteúdo de um arquivo"""
    import os
    caminho = state.arquivo_alvo
    if not os.path.exists(caminho):
        state.erro_tool = f"Arquivo {caminho} não encontrado"
        state.tool_ok = False
        return
    state.conteudo = open(caminho).read()
    state.tool_ok = True

@task(retry=2)
def buscar_web():
    """Simula busca na web"""
    termo = state.termo_busca
    state.resultado_busca = [
        {"titulo": f"Resultado 1 para {termo}", "url": f"ex.com/1"},
        {"titulo": f"Resultado 2 para {termo}", "url": f"ex.com/2"},
    ]
    state.tool_ok = True

@task()
def processar_texto():
    """Processa o texto lido ou buscado"""
    texto = state.get("conteudo") or str(state.get("resultado_busca", []))
    state.texto_processado = texto.upper()[:500]
    state.tool_ok = True

# ── Decisor (LLM simulado) ──────────────────────────────────

@task()
def raciocinar():
    """Simula o raciocínio do LLM: decide qual ferramenta chamar"""
    passo = len(state.historico)
    state.pensamento = f"Passo {passo}: analisando {state.objetivo}..."

    # Lógica simples de decisão
    if state.get("arquivo_alvo") and not state.get("conteudo"):
        state.proxima_acao = "ler_arquivo"
    elif state.get("termo_busca") and not state.get("resultado_busca"):
        state.proxima_acao = "buscar_web"
    elif state.get("conteudo") or state.get("resultado_busca"):
        if not state.get("texto_processado"):
            state.proxima_acao = "processar_texto"
        else:
            state.proxima_acao = "responder"
    else:
        state.proxima_acao = "responder"

    state.historico.append({
        "passo": passo,
        "pensamento": state.pensamento,
        "acao": state.proxima_acao,
    })

@task()
def responder():
    """Gera a resposta final"""
    state.resposta_final = (
        f"Objetivo: {state.objetivo}\n"
        f"Passos executados: {len(state.historico)}\n"
        f"Texto processado: {state.texto_processado[:200]}"
    )
    state.concluido = True

def registrar_acao():
    """Registra no histórico qual ação foi tomada"""
    ultimo = state.historico[-1]
    ultimo["resultado"] = "ok" if state.tool_ok else f"erro: {state.erro_tool}"

# ── Flow principal ──────────────────────────────────────────

@flow
def agente_react():
    """Agente ReAct: raciocina → age → observa → repete"""

    while not state.concluido:
        raciocinar()

        if state.proxima_acao == "ler_arquivo":
            ler_arquivo()
            registrar_acao()

        elif state.proxima_acao == "buscar_web":
            buscar_web()
            registrar_acao()

        elif state.proxima_acao == "processar_texto":
            processar_texto()
            registrar_acao()

        elif state.proxima_acao == "responder":
            responder()

# ── Execução ────────────────────────────────────────────────

resultado = agente_react.run(
    objetivo="Ler o arquivo config.txt e processar seu conteúdo",
    arquivo_alvo="config.txt",
    historico=[],
    concluido=False,
)

print(resultado.resposta_final)
```

**Conceitos:** loop `while`, roteamento condicional, `@task(retry)`, histórico em state.

---

## 2. Agente de Pesquisa e Síntese

Agente que pesquisa múltiplas fontes em paralelo, extrai informações e sintetiza uma resposta.

```python
from apex.graph import flow, task, state, parallel

# ── Fontes de dados ─────────────────────────────────────────

@task(timeout=10)
def buscar_api():
    """Busca em API externa"""
    import time
    time.sleep(0.1)  # simulando latência
    state.dados_api = {"fonte": "api", "dados": "Resultados da API"}
    state.fontes_consultadas.append("api")

@task(timeout=15)
def buscar_banco():
    """Busca em banco de dados local"""
    import time
    time.sleep(0.2)
    state.dados_banco = {"fonte": "banco", "dados": "Registros do BD"}
    state.fontes_consultadas.append("banco")

@task(timeout=5)
def buscar_cache():
    """Busca em cache"""
    # Cache simulado
    state.dados_cache = {"fonte": "cache", "dados": "Dados em cache"}
    state.fontes_consultadas.append("cache")

# ── Pós-processamento ───────────────────────────────────────

@task()
def consolidar():
    """Junta resultados de todas as fontes"""
    todos_dados = []
    for fonte in state.fontes_consultadas:
        chave = f"dados_{fonte}"
        if state.get(chave):
            todos_dados.append(state.get(chave))

    state.base_conhecimento = todos_dados
    state.total_fontes = len(todos_dados)

@task()
def analisar():
    """Analisa e extrai insights"""
    state.insights = []
    for item in state.base_conhecimento:
        state.insights.append(f"De {item['fonte']}: {item['dados']}")

@task()
def sintetizar():
    """Gera resposta final consolidada"""
    state.resposta = "\n".join([
        f"Pesquisa: {state.pergunta}",
        f"Fontes consultadas: {state.total_fontes}",
        "---",
        *[f"• {i}" for i in state.insights],
    ])
    state.concluido = True

# ── Flow ────────────────────────────────────────────────────

@flow
def agente_pesquisa():
    """Pesquisa múltiplas fontes em paralelo e sintetiza"""

    # Dispara todas as buscas simultaneamente
    with parallel():
        buscar_api()
        buscar_banco()
        buscar_cache()

    # Processa os resultados
    consolidar()

    # Se encontrou dados, analisa e responde
    if state.base_conhecimento:
        analisar()
        sintetizar()
    else:
        state.resposta = "Nenhuma fonte disponível."
        state.concluido = True

# ── Execução ────────────────────────────────────────────────

resultado = agente_pesquisa.run(
    pergunta="Qual a última versão do Python?",
    fontes_consultadas=[],
    concluido=False,
)

print(resultado.resposta)

# Visualização
print(agente_pesquisa.viz("mermaid"))
```

**Conceitos:** `with parallel()`, timeout por task, consolidação pós-paralela, condicional pós-pesquisa.

---

## 3. Orquestrador de Subtarefas

Agente que recebe uma tarefa complexa, a decompõe em subtarefas e as executa com dependências.

```python
from apex.graph import flow, task, state, parallel

# ── Planejador ──────────────────────────────────────────────

@task()
def planejar():
    """Decompõe a tarefa em etapas menores"""
    state.etapas = [
        {"id": "validar",   "descricao": "Validar entrada",         "deps": []},
        {"id": "buscar",    "descricao": "Buscar dados",            "deps": ["validar"]},
        {"id": "enriquecer","descricao": "Enriquecer com fontes",   "deps": ["buscar"]},
        {"id": "calcular",  "descricao": "Calcular métricas",       "deps": ["enriquecer"]},
        {"id": "formatar",  "descricao": "Formatar saída",          "deps": ["calcular"]},
        {"id": "entregar",  "descricao": "Entregar resultado",      "deps": ["formatar"]},
    ]
    state.resultados_etapas = {}

# ── Executores ──────────────────────────────────────────────

@task(retry=2)
def validar():
    state.resultados_etapas["validar"] = {"status": "ok", "dados": state.entrada}

@task(retry=2, timeout=10)
def buscar():
    dados = f"Dados enriquecidos para: {state.entrada}"
    state.resultados_etapas["buscar"] = {"status": "ok", "dados": dados}

@task()
def enriquecer():
    base = state.resultados_etapas["buscar"]["dados"]
    state.resultados_etapas["enriquecer"] = {
        "status": "ok",
        "dados": base + " + fontes externas"
    }

@task(timeout=5)
def calcular():
    state.resultados_etapas["calcular"] = {
        "status": "ok",
        "métricas": {"total": 42, "media": 21.0, "min": 0, "max": 100}
    }

@task()
def formatar():
    metricas = state.resultados_etapas["calcular"]["métricas"]
    state.resultados_etapas["formatar"] = {
        "status": "ok",
        "relatorio": (
            f"Relatório para: {state.entrada}\n"
            f"Total: {metricas['total']}\n"
            f"Média: {metricas['media']}\n"
        )
    }

@task()
def entregar():
    relatorio = state.resultados_etapas["formatar"]["relatorio"]
    state.relatorio_final = relatorio
    state.concluido = True

# ── Mapeamento de tarefas ──────────────────────────────────

MAP = {
    "validar": validar,
    "buscar": buscar,
    "enriquecer": enriquecer,
    "calcular": calcular,
    "formatar": formatar,
    "entregar": entregar,
}

def executar_etapa(etapa_id: str):
    MAP[etapa_id]()

# ── Flow ────────────────────────────────────────────────────

@flow
def orquestrador():
    """Orquestrador inteligente: planeja, executa com dependências, entrega"""

    planejar()

    # Barreira 1: validação (sem dependências)
    executar_etapa("validar")

    # Barreira 2: busca (depende de validar)
    if state.resultados_etapas["validar"]["status"] == "ok":
        executar_etapa("buscar")

    # Barreira 3: enriquecer (depende de buscar)
    if state.resultados_etapas.get("buscar", {}).get("status") == "ok":
        executar_etapa("enriquecer")

    # Barreira 4: calcular (depende de enriquecer)
    if state.resultados_etapas.get("enriquecer", {}).get("status") == "ok":
        executar_etapa("calcular")

    # Barreira 5: formatar (depende de calcular)
    if state.resultados_etapas.get("calcular", {}).get("status") == "ok":
        executar_etapa("formatar")

    # Barreira 6: entregar (depende de formatar)
    if state.resultados_etapas.get("formatar", {}).get("status") == "ok":
        executar_etapa("entregar")

# ── Execução ────────────────────────────────────────────────

resultado = orquestrador.run(
    entrada="Processar pedido #1234",
    concluido=False,
)

print(resultado.relatorio_final)
```

**Conceitos:** planejamento dinâmico, barreiras de dependência, `@task` com timeout, dicionário de tarefas.

---

## 4. Agente com Memória de Curto Prazo

Agente que mantém contexto entre iterações usando o state como memória episódica.

```python
from apex.graph import flow, task, state

@task()
def perceber():
    """Percebe o ambiente — lê o estímulo atual"""
    state.estimulo_atual = state.fila_estimulos.pop(0) if state.fila_estimulos else None

@task()
def recuperar_contexto():
    """Recupera contexto relevante da memória"""
    if not state.memoria:
        state.contexto = "Nenhum histórico disponível."
        return

    ultimos = state.memoria[-3:]
    state.contexto = "\n".join([
        f"[{m['tempo']}] Ação: {m['acao']} → Resultado: {m['resultado']}"
        for m in ultimos
    ])

@task()
def raciocinar():
    """Decide a próxima ação baseado em estímulo + contexto"""
    if not state.estimulo_atual:
        state.prox_acao = "dormir"
        return

    estado_atual = {
        "estimulo": state.estimulo_atual,
        "contexto": state.contexto,
        "ciclo": state.ciclo_atual,
    }
    state.estado_atual = estado_atual

    # Lógica de decisão
    if "erro" in state.estimulo_atual.lower():
        state.prox_acao = "corrigir"
    elif state.estimulo_atual == state.get("ultimo_estimulo"):
        state.prox_acao = "ignorar"
    else:
        state.prox_acao = "processar"

@task()
def executar_acao():
    """Executa a ação decidida"""
    acao = state.prox_acao
    state.acao_executada = acao

    if acao == "processar":
        state.ultimo_resultado = f"Processado: {state.estimulo_atual}"
    elif acao == "corrigir":
        state.ultimo_resultado = f"Corrigido: {state.estimulo_atual}"
    elif acao == "ignorar":
        state.ultimo_resultado = f"Ignorado (duplicata)"
    else:
        state.ultimo_resultado = "Sem ação"

@task()
def memorizar():
    """Armazena a experiência na memória episódica"""
    state.memoria.append({
        "tempo": state.ciclo_atual,
        "estimulo": state.estimulo_atual,
        "acao": state.acao_executada,
        "resultado": state.ultimo_resultado,
    })
    state.ultimo_estimulo = state.estimulo_atual
    state.ciclo_atual += 1

@task()
def dormir():
    """Estado de repouso — aguarda novos estímulos"""
    state.em_repouso = True

# ── Flow ────────────────────────────────────────────────────

@flow
def agente_memoria():
    """Agente com memória episódica: percebe → recupera → raciocina → age → memoriza"""

    while not state.em_repouso and state.fila_estimulos:
        perceber()
        if not state.estimulo_atual:
            dormir()
        else:
            recuperar_contexto()
            raciocinar()
            executar_acao()
            memorizar()

# ── Execução ────────────────────────────────────────────────

resultado = agente_memoria.run(
    fila_estimulos=[
        "Novo pedido #1",
        "Erro na validação",
        "Novo pedido #2",
        "Novo pedido #2",    # duplicata proposital
        "Finalizar lote",
    ],
    memoria=[],
    ciclo_atual=0,
    em_repouso=False,
)

print(f"Total de ciclos: {resultado.ciclo_atual}")
print(f"Memória ({len(resultado.memoria)} episódios):")
for m in resultado.memoria:
    print(f"  [{m['tempo']}] {m['acao']:12s} | {m['estimulo'][:30]}")
```

**Conceitos:** memória episódica no state, ciclo percepção-ação, detecção de duplicatas, estado de repouso.

---

## Resumo dos padrões

| Padrão | Técnicas | Complexidade |
|--------|----------|--------------|
| ReAct com ferramentas | Loop, condicional, retry, histórico | Média |
| Pesquisa e síntese | Paralelismo, timeout, consolidação | Média |
| Orquestrador de subtarefas | Planejamento dinâmico, barreiras | Média-Alta |
| Memória episódica | State como memória, ciclo感知-ação | Média |
