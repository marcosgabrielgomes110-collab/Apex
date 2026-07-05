# Changelog

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