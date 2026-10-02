# Changelog

## [Não publicado]

Correção dos caminhos de subflow, paralelismo e control-flow — todos falhavam
em silêncio ou com erro enganoso. Cobertura nova em `tests/test_regressions.py`
e execução dos exemplos da doc em `tests/test_docs_examples.py`.

### Corrigido
- **Subflows**: `@flow` chamando `@flow` não era detectado como subflow (o
  atributo era lido do objeto errado). O flow interno recebia um state vazio,
  apagava o state do pai, e o `State` retornado era gravado dentro de si mesmo
  — `to_dict()` estourava com `RecursionError`, assim como qualquer `if`
  depois de um subflow.
- **`with parallel()` ignorava `if`/`while`**: nós de control-flow dentro do
  bloco eram marcados como executados sem avaliar a condição — o corpo rodava
  incondicionalmente e loops rodavam uma vez.
- **Merge de estado no paralelismo**: escritas em chaves já existentes eram
  descartadas em silêncio. Agora o merge é last-write-wins determinístico, na
  ordem dos branches, com `UserWarning` em conflito.
- **Cadeias `if/elif/else`**: ramos que um `elif` aninhado acabara de bloquear
  eram desbloqueados e executados — mais de um ramo rodava.
- **Loops com `if` no corpo**: nas iterações seguintes o bloqueio da iteração
  anterior não era desfeito, e ambos os ramos podiam rodar.
- **`timeout` não interrompia nada**: o `ThreadPoolExecutor` esperava a task
  terminar antes de levantar. Agora levanta `FlowTimeoutError` na hora, com a
  task isolada num snapshot cujas escritas parciais são descartadas.
- **`State.__init__` com dict vazio**: `data or {}` criava um dict novo, então
  `state.nested[k] = v` se perdia quando `nested` era `{}`.
- **Chamadas que não eram task**: `print()`, `len()`, `obj.metodo()` e
  atribuições (`state.x += 1`) levantavam `NameError` ou eram ignoradas em
  silêncio. Viram nós inline; `x = task()` agora executa e grava em `state.x`;
  tasks aceitam argumentos; `def` dentro do corpo do flow é resolvido.
- **Condições falhavam em silêncio**: `if` com chave ausente ou nome indefinido
  retornava `False` (só avisava com `APEX_DEBUG`, removido). Agora levanta
  `FlowConditionError`; `state["chave"]`, `state.get()` e dicts aninhados
  funcionam nas condições.
- **Vazamento de state**: o `ContextVar` não era restaurado ao fim do `run()`,
  contaminando execuções seguintes.

### Alterado (breaking)
- `Flow.run()` devolve o state da própria execução e restaura o contexto ao
  sair: leia `resultado.chave`, não o `state` depois do run.
- Exceções de task agora são `FlowTaskError` (subclasse de `RuntimeError`, com
  a causa original em `__cause__`); timeout é `FlowTimeoutError` (também
  `TimeoutError`). Todas exportadas em `apex.graph`.

### Removido
- `_run_parallel_group` (inalcançável) e o fallback de `ast.unparse` para
  Python < 3.9.

### Empacotamento
- Versão com fonte única (`apex/__version__.py`) via `dynamic` no pyproject.
- Extra `[png]` para `cairosvg` e `[dev]` para pytest; `setup.py` removido.
- `.gitignore` não ignora mais todos os dotfiles (quebrava `.github/`).
- `exemples/` renomeado para `examples/`.

## [0.1.1] — 2026-07-04

### Adicionado
- `State.get(key, default=None)` — acesso seguro com fallback
- `State.__delitem__` — suporte a `del state["chave"]`

### Corrigido
- Nome de retorno de tasks: usa `fn.__name__` em vez de heurística frágil de sufixo
- Isolamento de estado em tasks paralelas: cada thread recebe snapshot independente com merge ao final
- Exemplos: `graph_demo.py` corrigido de `Pyram.graph` para `apex.graph`
- Exemplos removidos: `tool_calling.py` e `test_.py` (módulos inexistentes)
- Limpeza de `sys.path.insert` redundante nos arquivos de teste
- Variável de debug renomeada: `PYRAM_DEBUG` → `APEX_DEBUG`

## [0.1.0] — Primeiro release

### Motor core
- `@flow` — decorator que analisa AST e constrói DAG automaticamente
- `@task(retry, timeout)` — configuração de retry com backoff e timeout
- `state` — estado global implícito via `contextvars`, thread-safe
- `Flow.run()` — execução com paralelismo automático (topological sort)
- `Flow.viz()` — visualização em 5 formatos: ASCII, SVG, Mermaid, HTML, PNG
- `parallel()` — context manager para paralelismo explícito

### DAG
- Suporte a condicionais (`if/else`) com merge implícito
- Suporte a loops (`while`) com back-edge e limite de segurança
- Subflows: um `@flow` pode chamar outro `@flow`
- Detecção de ciclos via Kahn topological sort