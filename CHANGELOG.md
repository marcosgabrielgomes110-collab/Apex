# Changelog

## [0.2.0] — 2026-10-28

### Corrigido
- Subflow compartilha o `State` do pai (antes criava estado novo e apagava chaves gravadas antes do subflow)
- Controle de fluxo aninhado (`if`/`while`/`parallel` dentro de branch/loop) é executado corretamente
- Timeout responde no limite (antes bloqueava até a task terminar); a thread órfã ainda roda até o fim, mas escreve em snapshot descartado
- Merge paralelo determinístico com detecção de conflito (escrita concorrente na mesma chave levanta erro claro, sem descarte silencioso)
- Escaping de SVG/Mermaid/HTML (nomes/condições com `<`, `&`, `#`, etc.) e declaração UTF-8 nos arquivos
- `async def` em `@task`/`@flow` levanta `TypeError` (antes era no-op silencioso com coroutine nunca awaited)
- Retorno de task usa nome único por nó (sem sobrescrever silenciosamente); colisão com chave pré-existente gera aviso
- Condições inválidas (chave ausente/nome inexistente) falham alto em vez de virarem `False`/`None` silenciosamente

### Adicionado
- `Flow.run_detailed()` → `RunResult` (`state`, `results`, `duration`, `cancelled`, `errors`)
- `Flow.run(cancel_event=...)` — cancelamento cooperativo entre nós; `CancelledError` exportado
- Lock no build do DAG (`_ensure_dag`) e restauração do `contextvars` após `run()` — sem vazar o último estado para a thread/contexto de fora

### Visualização
- Grafo vazio coerente nos 5 formatos (mensagem `(empty graph)`)
- Largura de nó calculada pelo maior label; truncamento configurável com reticências em vez de corte fixo em 18 caracteres

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