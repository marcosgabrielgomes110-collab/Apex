<p align="center">
  <picture>
    <img src="../images/Apex.png" alt="Apex Logo" width="100"/>
  </picture>
  <br>
  <strong>Agentes Autônomos — Arquiteturas Complexas</strong>
</p>

---

> Exemplos de alta complexidade: sistemas multi-agente, cadeias de ferramentas com fallback, workflows adaptativos e loops aninhados com estados globais.

---

## Índice

- [1. Supervisor Multi-Agente](#1-supervisor-multi-agente)
- [2. Pipeline Adaptativo com Fallback](#2-pipeline-adaptativo-com-fallback)
- [3. Máquina de Estados com Subflows](#3-máquina-de-estados-com-subflows)
- [4. Cadeia de Ferramentas com Rollback](#4-cadeia-de-ferramentas-com-rollback)

---

## 1. Supervisor Multi-Agente

Um **agente supervisor** que delega tarefas a agentes especializados, coleta resultados e toma decisões de coordenação.

```python
from apex.graph import flow, task, state, parallel

# ═══════════════════════════════════════════════════════════════
# Agentes especializados (cada um é um subflow)
# ═══════════════════════════════════════════════════════════════

@flow
def agente_analise():
    """Agente que analisa dados brutos"""
    def extrair_metricas():
        state.metricas_brutas = {
            "total": len(state.dados_brutos),
            "valores": [item["valor"] for item in state.dados_brutos],
        }
    extrair_metricas()

    def calcular_estatisticas():
        vals = state.metricas_brutas["valores"]
        state.estatisticas = {
            "media": sum(vals) / len(vals) if vals else 0,
            "max": max(vals) if vals else 0,
            "min": min(vals) if vals else 0,
        }
    calcular_estatisticas()

    def classificar_prioridade():
        media = state.estatisticas["media"]
        if media > 80:
            state.prioridade = "alta"
        elif media > 50:
            state.prioridade = "media"
        else:
            state.prioridade = "baixa"
    classificar_prioridade()

@flow
def agente_verificacao():
    """Agente que verifica consistência dos dados"""
    def checar_integridade():
        erros = []
        for item in state.dados_brutos:
            if "id" not in item:
                erros.append(f"Item sem id: {item}")
            if "valor" not in item:
                erros.append(f"Item {item.get('id', '?')} sem valor")
        state.erros_validacao = erros
        state.integridade_ok = len(erros) == 0
    checar_integridade()

    def checar_duplicatas():
        ids = [item["id"] for item in state.dados_brutos if "id" in item]
        state.duplicatas = [id_ for id_ in ids if ids.count(id_) > 1]
        state.sem_duplicatas = len(state.duplicatas) == 0
    checar_duplicatas()

@flow
def agente_relatorio():
    """Agente que gera relatório final"""
    def montar_sumario():
        linhas = [
            f"Relatório de Processamento",
            f"=========================",
            f"Total de itens: {state.metricas_brutas['total']}",
            f"Média: {state.estatisticas['media']:.2f}",
            f"Prioridade: {state.prioridade}",
            f"Integridade: {'OK' if state.integridade_ok else 'FALHAS'}",
        ]
        if state.get("resumo_acao"):
            linhas.append(f"Ação: {state.resumo_acao}")
        state.relatorio = "\n".join(linhas)
    montar_sumario()

# ═══════════════════════════════════════════════════════════════
# Supervisor
# ═══════════════════════════════════════════════════════════════

@task()
def definir_escopo():
    """Supervisor define o que cada agente deve fazer"""
    state.escopo = {
        "analise": True,
        "verificacao": True,
        "relatorio": True,
    }

@task()
def consolidar_resultados():
    """Reúne resultados de todos os agentes"""
    state.resultado_consolidado = {
        "estatisticas": state.estatisticas,
        "prioridade": state.prioridade,
        "valido": state.integridade_ok and state.sem_duplicatas,
        "erros": state.erros_validacao,
        "duplicatas": state.duplicatas,
    }

@task()
def decidir_acao():
    """Supervisor decide o que fazer com base nos resultados"""
    cons = state.resultado_consolidado
    if not cons["valido"]:
        state.resumo_acao = "REJEITADO — correção necessária"
    elif cons["prioridade"] == "alta":
        state.resumo_acao = "APROVADO — encaminhar para diretoria"
    elif cons["prioridade"] == "media":
        state.resumo_acao = "APROVADO — arquivar"
    else:
        state.resumo_acao = "APROVADO — baixa prioridade, armazenar"

@flow
def supervisao():
    """Flow principal: orquestra agentes especializados"""

    definir_escopo()

    # Dispara agentes em paralelo
    with parallel():
        if state.escopo["analise"]:
            agente_analise()
        if state.escopo["verificacao"]:
            agente_verificacao()

    # Barreira: ambos precisam terminar
    consolidar_resultados()
    decidir_acao()

    # Relatório final
    if state.escopo["relatorio"]:
        agente_relatorio()

# ═══════════════════════════════════════════════════════════════
# Execução
# ═══════════════════════════════════════════════════════════════

resultado = supervisao.run(dados_brutos=[
    {"id": "A1", "valor": 95},
    {"id": "A2", "valor": 72},
    {"id": "A3", "valor": 88},
    {"id": "A4", "valor": 45},
])

print(resultado.relatorio)
print(f"\nAção do supervisor: {resultado.resumo_acao}")
```

**Conceitos:** subflows como agentes, `with parallel()` com condicionais, supervisor centralizado, consolidação pós-paralela.

---

## 2. Pipeline Adaptativo com Fallback

Pipeline que **testa caminhos alternativos** quando uma etapa falha, com fallback progressivo.

```python
from apex.graph import flow, task, state, parallel
import random

# ═══════════════════════════════════════════════════════════════
# Provedores de dados (alguns falham)
# ═══════════════════════════════════════════════════════════════

@task(retry=1, timeout=5)
def provedor_principal():
    """Fonte primária de dados (pode falhar)"""
    if random.random() < 0.6:
        raise ConnectionError("Fonte principal indisponível")
    state.dados_brutos = {"fonte": "principal", "dados": "dados da fonte principal"}
    state.fonte_ativa = "principal"

@task(retry=1, timeout=5)
def provedor_secundario():
    """Fonte secundária (fallback)"""
    if random.random() < 0.3:
        raise ConnectionError("Fonte secundária indisponível")
    state.dados_brutos = {"fonte": "secundaria", "dados": "dados da fonte secundária"}
    state.fonte_ativa = "secundaria"

@task()
def provedor_cache():
    """Último recurso — dados em cache"""
    state.dados_brutos = {"fonte": "cache", "dados": "dados em cache (podem estar desatualizados)"}
    state.fonte_ativa = "cache"
    state.cache_usado = True

# ═══════════════════════════════════════════════════════════════
# Processamento adaptável
# ═══════════════════════════════════════════════════════════════

@task()
def validar_dados():
    """Valida os dados recebidos (diferente para cada fonte)"""
    fonte = state.fonte_ativa
    dados = state.dados_brutos["dados"]

    if fonte == "cache":
        state.dados_validos = False
        state.motivo_rejeicao = "Cache pode estar desatualizado — usando mesmo assim"
        return

    state.dados_validos = True
    state.dados_processados = dados.upper()

@task()
def enriquecer():
    """Enriquece com dados adicionais"""
    base = state.dados_processados
    state.dados_enriquecidos = f"{base} | enriquecido às {__import__('time').time():.0f}"

@task()
def finalizar():
    state.resultado_final = state.dados_enriquecidos
    state.concluido = True

# ═══════════════════════════════════════════════════════════════
# Flow adaptativo
# ═══════════════════════════════════════════════════════════════

@flow
def pipeline_adaptativo():
    """Pipeline que tenta fontes em ordem decrescente de qualidade"""

    state.fonte_ativa = None

    # Tentativa 1: fonte principal
    try:
        provedor_principal()
    except Exception:
        pass

    # Fallback 1: se principal falhou, tenta secundária
    if not state.fonte_ativa:
        try:
            provedor_secundario()
        except Exception:
            pass

    # Fallback 2: se ambas falharam, usa cache
    if not state.fonte_ativa:
        provedor_cache()

    # Se ainda assim não tem dados, aborta
    if not state.fonte_ativa:
        state.erro = "Todas as fontes falharam"
        state.concluido = True
        return

    # Processa com validação adaptativa
    validar_dados()
    enriquecer()
    finalizar()

# ═══════════════════════════════════════════════════════════════
# Execução (múltiplas tentativas para demonstrar fallback)
# ═══════════════════════════════════════════════════════════════

import os
random.seed(42)

for tentativa in range(3):
    state._set_state(state.State({"concluido": False, "fonte_ativa": None}))
    resultado = pipeline_adaptativo.run(concluido=False)
    print(f"Tentativa {tentativa + 1}: fonte={resultado.get('fonte_ativa', 'N/A')}, "
          f"ok={resultado.get('concluido', False)}")
```

**Conceitos:** `try/except` em tasks, cadeia de fallback, decisões adaptativas no flow.

---

## 3. Máquina de Estados com Subflows

Workflow que se comporta como uma **máquina de estados finita**, onde cada estado é um subflow e as transições são condicionais.

```python
from apex.graph import flow, task, state

# ═══════════════════════════════════════════════════════════════
# Estados (cada um é um subflow)
# ═══════════════════════════════════════════════════════════════

@flow
def estado_inicial():
    """Estado: INIT — valida entrada e decide próximo"""
    def validar_entrada():
        state.erro = None
        if not state.get("pedido"):
            state.erro = "Pedido não informado"
            state.proximo_estado = "erro"
            return
        state.pedido_validado = state.pedido
        state.proximo_estado = "processando"
    validar_entrada()

@flow
def estado_processando():
    """Estado: PROCESS — executa o processamento principal"""
    def executar():
        import time
        state.inicio = time.time()
        state.resultado_intermediario = f"Processado: {state.pedido_validado}"
        state.proximo_estado = "validacao"
    executar()

@flow
def estado_validacao():
    """Estado: VALIDATE — valida resultado e decide continuar ou corrigir"""
    def validar_resultado():
        resultado = state.resultado_intermediario
        if not resultado:
            state.proximo_estado = "erro"
            state.erro = "Resultado vazio"
            return
        state.proximo_estado = "finalizando"
    validar_resultado()

@flow
def estado_finalizando():
    """Estado: FINISH — prepara saída"""
    def preparar_saida():
        state.saida_final = {
            "pedido": state.pedido_validado,
            "resultado": state.resultado_intermediario,
            "timestamp": __import__('time').time(),
        }
        state.proximo_estado = "concluido"
    preparar_saida()

@flow
def estado_erro():
    """Estado: ERROR — trata erro e decide recovery"""
    def tratar_erro():
        state.saida_final = {"erro": state.erro, "pedido": state.get("pedido")}
        state.proximo_estado = "concluido"
    tratar_erro()

# ═══════════════════════════════════════════════════════════════
# Máquina de estados
# ═══════════════════════════════════════════════════════════════

@flow
def workflow_estados():
    """Máquina de estados: cada estado decide o próximo dinamicamente"""

    state.proximo_estado = "inicial"

    while state.proximo_estado not in ("concluido", None):
        if state.proximo_estado == "inicial":
            estado_inicial()
        elif state.proximo_estado == "processando":
            estado_processando()
        elif state.proximo_estado == "validacao":
            estado_validacao()
        elif state.proximo_estado == "finalizando":
            estado_finalizando()
        elif state.proximo_estado == "erro":
            estado_erro()

        if state.proximo_estado == state.get("_ultimo_estado"):
            state.erro_maquina = f"Loop infinito detectado em {state.proximo_estado}"
            break
        state._ultimo_estado = state.proximo_estado

# ═══════════════════════════════════════════════════════════════
# Execução
# ═══════════════════════════════════════════════════════════════

resultado = workflow_estados.run(pedido="PEDIDO-2024-001")
print("Saída final:")
print(resultado.saida_final)
```

**Conceitos:** máquina de estados com subflows, transição dinâmica via state, detecção de loop infinito.

---

## 4. Cadeia de Ferramentas com Rollback

Workflow que executa uma sequência de operações e, em caso de falha, **desfaz as operações anteriores** (rollback).

```python
from apex.graph import flow, task, state

# ═══════════════════════════════════════════════════════════════
# Operações (cada uma pode falhar)
# ═══════════════════════════════════════════════════════════════

@task(retry=1)
def criar_diretorio():
    """Operação 1: cria diretório"""
    import os
    dir_name = state.workspace
    os.makedirs(dir_name, exist_ok=True)
    state.operacoes_executadas.append("criar_diretorio")
    print(f"  ✓ Criado diretório: {dir_name}")

@task(retry=1)
def copiar_arquivos():
    """Operação 2: copia arquivos"""
    import shutil, os
    os.makedirs(f"{state.workspace}/src", exist_ok=True)
    # Simula cópia
    with open(f"{state.workspace}/src/dados.txt", "w") as f:
        f.write(state.conteudo_arquivo)
    state.operacoes_executadas.append("copiar_arquivos")
    print(f"  ✓ Copiados arquivos para {state.workspace}/src")

@task(retry=1)
def compilar():
    """Operação 3: compila (pode falhar)"""
    if state.get("forcar_falha_compilacao"):
        raise RuntimeError("Erro de compilação: sintaxe inválida")
    state.operacoes_executadas.append("compilar")
    print("  ✓ Compilação bem-sucedida")

@task(retry=1)
def executar_testes():
    """Operação 4: executa testes (pode falhar)"""
    if state.get("forcar_falha_teste"):
        raise RuntimeError("Teste falhou: assert esperado 42, recebeu 0")
    state.operacoes_executadas.append("executar_testes")
    print("  ✓ Testes passaram")

@task(retry=1)
def fazer_deploy():
    """Operação 5: deploy"""
    state.operacoes_executadas.append("fazer_deploy")
    state.deploy_concluido = True
    print("  ✓ Deploy realizado")

# ═══════════════════════════════════════════════════════════════
# Rollbacks
# ═══════════════════════════════════════════════════════════════

@task()
def rollback_criar_diretorio():
    import shutil
    shutil.rmtree(state.workspace, ignore_errors=True)
    print(f"  ✗ Rollback: removido {state.workspace}")

@task()
def rollback_copiar_arquivos():
    import shutil
    shutil.rmtree(f"{state.workspace}/src", ignore_errors=True)
    print(f"  ✗ Rollback: removido {state.workspace}/src")

@task()
def rollback_compilar():
    print("  ✗ Rollback compilar: limpando artefatos")
    import glob, os
    for f in glob.glob(f"{state.workspace}/**/*.o", recursive=True):
        os.remove(f)

# ── Mapa de rollbacks ────────────────────────────────────────

ROLLBACK_MAP = {
    "criar_diretorio": rollback_criar_diretorio,
    "copiar_arquivos": rollback_copiar_arquivos,
    "compilar": rollback_compilar,
}

# ═══════════════════════════════════════════════════════════════
# Flow principal com rollback automático
# ═══════════════════════════════════════════════════════════════

@flow
def pipeline_rollback():
    """Pipeline que desfaz operações anteriores em caso de falha"""

    state.operacoes_executadas = []
    state.deploy_concluido = False
    state.erro_pipeline = None

    try:
        criar_diretorio()
        copiar_arquivos()

        try:
            compilar()
        except Exception:
            state.erro_pipeline = "Falha na compilação"
            raise

        try:
            executar_testes()
        except Exception:
            state.erro_pipeline = "Falha nos testes"
            raise

        fazer_deploy()

    except Exception:
        # Rollback em ordem reversa
        print(f"\n  ! Erro: {state.erro_pipeline}")
        print("  ! Iniciando rollback...\n")
        for op in reversed(state.operacoes_executadas):
            if op in ROLLBACK_MAP:
                try:
                    ROLLBACK_MAP[op]()
                except Exception as rb_err:
                    print(f"  ! Falha no rollback de {op}: {rb_err}")

# ═══════════════════════════════════════════════════════════════
# Execução
# ═══════════════════════════════════════════════════════════════

# Caso 1: sucesso
print("=== Caso 1: Pipeline bem-sucedido ===")
pipeline_rollback.run(
    workspace="/tmp/apex_deploy",
    conteudo_arquivo="print('hello')",
    forcar_falha_compilacao=False,
    forcar_falha_teste=False,
)

print()

# Caso 2: falha com rollback
print("=== Caso 2: Falha com rollback ===")
pipeline_rollback.run(
    workspace="/tmp/apex_deploy",
    conteudo_arquivo="print('hello')",
    forcar_falha_compilacao=True,
    forcar_falha_teste=False,
)
```

**Conceitos:** `try/except` no flow, rollback ordenado reverso, mapa de compensações, tolerância a falhas.

---

## Comparação de Complexidade

| Padrão | Subflows | Aninhamento | Técnicas-chave | Complexidade |
|--------|----------|-------------|----------------|--------------|
| **Supervisor Multi-Agente** | 4 | 2 níveis | Subflows, paralelismo condicional, consolidação | ⭐⭐⭐ |
| **Pipeline Adaptativo** | 0 | 1 nível | Cadeia de fallback, try/except em tasks | ⭐⭐⭐ |
| **Máquina de Estados** | 6 | 2 níveis | Subflows como estados, transição dinâmica, detecção de loop | ⭐⭐⭐⭐ |
| **Cadeia com Rollback** | 0 | 3 níveis | Try/except aninhado, rollback reverso, mapa de compensações | ⭐⭐⭐⭐ |
