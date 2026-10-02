from __future__ import annotations

import threading
import time
import warnings
from typing import Any, Callable

from ._dag import DAG, Node, NodeConfig, build_dag
from ._state import State, _set_state, _reset_state

MAX_LOOP_ITERATIONS = 100


class FlowError(RuntimeError):
    """Erro genérico de execução de um flow."""


class FlowConditionError(FlowError):
    """Falha ao avaliar a condição de um `if`/`while`."""


class FlowTaskError(FlowError):
    """Falha ao executar uma task do flow."""


class FlowTimeoutError(FlowError, TimeoutError):
    """Task excedeu o timeout configurado."""


class _EvalProxy:
    """Snapshot somente-leitura do state para avaliação de condições."""

    def __init__(self, data: dict):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        data = object.__getattribute__(self, "_data")
        if name not in data:
            # chave ausente NÃO vira None silenciosamente: um typo na condição
            # tem que falhar alto, não escolher o else
            raise AttributeError(
                f"State key '{name}' not found while evaluating a condition"
            )
        return self._wrap(data[name])

    def __getitem__(self, key: str) -> Any:
        data = object.__getattribute__(self, "_data")
        return self._wrap(data[key])

    def get(self, key: str, default: Any = None) -> Any:
        data = object.__getattribute__(self, "_data")
        if key not in data:
            return default
        return self._wrap(data[key])

    def __contains__(self, key: str) -> bool:
        return key in object.__getattribute__(self, "_data")

    def __iter__(self):
        return iter(object.__getattribute__(self, "_data"))

    def __len__(self) -> int:
        return len(object.__getattribute__(self, "_data"))

    @staticmethod
    def _wrap(val: Any) -> Any:
        return _EvalProxy(val) if isinstance(val, dict) else val

    def __bool__(self) -> bool:
        return bool(object.__getattribute__(self, "_data"))


class Flow:
    """Workflow executável. Criado pelo decorator @flow."""

    def __init__(self, func: Callable, *, name: str = ""):
        self._func = func
        self._name = name or func.__name__
        self._dag: DAG | None = None
        # marca a função E o Flow: o DAG builder resolve o nome para o objeto
        # `Flow`, por isso o atributo precisa existir nos dois.
        func._flow_dag = True
        self._flow_dag = True

    def _ensure_dag(self) -> DAG:
        if self._dag is None:
            self._dag = build_dag(self._func)
        return self._dag

    def run(self, state: dict | None = None, **kwargs) -> State:
        dag = self._ensure_dag()
        if isinstance(state, State):
            st = state
        else:
            data = dict(state or {})
            data.update(kwargs)
            st = State(data)

        token = _set_state(st)
        try:
            if not dag.nodes:
                self._func()
            else:
                _Scheduler(
                    dag, st,
                    globals_ns=getattr(self._func, "__globals__", {}),
                    tag=self._name,
                ).run()
        finally:
            _reset_state(token)

        return st

    def viz(self, fmt: str = "ascii", path: str | None = None):
        from ._viz import render
        return render(self._ensure_dag(), fmt=fmt, path=path)

    def viz_svg(self, path: str) -> None:
        self.viz(fmt="svg", path=path)

    def viz_mermaid(self) -> str:
        return self.viz(fmt="mermaid")

    def viz_html(self, path: str) -> None:
        self.viz(fmt="html", path=path)

    def viz_png(self, path: str) -> None:
        self.viz(fmt="png", path=path)

    def map(self) -> DAG:
        return self._ensure_dag()

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def __repr__(self) -> str:
        return f"Flow({self._name!r})"


class _Scheduler:
    def __init__(self, dag: DAG, state: State, *,
                 globals_ns: dict | None = None, tag: str = ""):
        self._dag = dag
        self._state = state
        self._globals = globals_ns or {}
        self._tag = tag or dag.entry or "flow"
        self._executed: set[str] = set()
        self._blocked: set[str] = set()

    def run(self) -> None:
        for level in self._dag._levels():
            for node_name in level:
                self._run_node(node_name)

    # ── dispatch ───────────────────────────────────────────────

    def _run_node(self, node_name: str) -> None:
        if node_name in self._executed or node_name in self._blocked:
            return

        node = self._dag.nodes.get(node_name)
        if node is None:
            self._executed.add(node_name)
            return

        if node.kind == "conditional":
            self._run_conditional(node)
        elif node.kind == "loop":
            self._run_loop(node)
        elif node.kind == "parallel":
            self._run_parallel(node)
        elif node.fn is None:
            self._executed.add(node_name)
        else:
            self._run_task(node)

    # ── tasks ──────────────────────────────────────────────────

    def _run_task(self, node: Node) -> None:
        config = node.config or NodeConfig()
        tag = f"[{self._tag}.{node.name}]"
        attempt = 0

        while True:
            try:
                if config.timeout > 0:
                    value = self._call_with_timeout(node, config.timeout, tag)
                else:
                    value = self._call(node, self._state)
                break
            except Exception as exc:
                if attempt >= config.retry:
                    raise self._wrap(exc, tag) from exc
                attempt += 1
                time.sleep(2 ** (attempt - 1))

        self._store_return(node, value)
        self._executed.add(node.name)

    def _call(self, node: Node, state: State) -> Any:
        _set_state(state)
        if node.kind == "subflow":
            return node.fn(state=state)
        if node.arg_builder is not None:
            args, kwargs = node.arg_builder()
            return node.fn(*args, **kwargs)
        return node.fn()

    def _call_with_timeout(self, node: Node, timeout: float, tag: str) -> Any:
        """Executa a task em thread separada sobre um snapshot isolado.

        No timeout a thread é abandonada (não há como matá-la em Python) e o
        snapshot é descartado — nenhuma escrita parcial vaza para o state.
        """
        base = self._state.to_dict()
        snap = self._state.copy()
        box: dict = {}

        def _target():
            try:
                box["value"] = self._call(node, snap)
            except BaseException as exc:  # noqa: BLE001 - repassado ao caller
                box["error"] = exc

        thread = threading.Thread(
            target=_target, daemon=True, name=f"apex-{node.name}"
        )
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            raise FlowTimeoutError(f"Task {tag} excedeu timeout de {timeout}s")
        if "error" in box:
            raise box["error"]

        self._merge_states([snap], base)
        return box.get("value")

    def _store_return(self, node: Node, value: Any) -> None:
        """Grava o retorno da task no state (``state.nome_da_task``)."""
        if value is None or node.fn is None or node.kind == "subflow":
            return
        if isinstance(value, State):
            # nunca guardar um State dentro do state: cria auto-referência
            return
        name = node.assign_to or getattr(node.fn, "__name__", None) or node.name
        setattr(self._state, name, value)
        _set_state(self._state)

    def _wrap(self, exc: Exception, tag: str) -> Exception:
        if isinstance(exc, FlowError):
            return exc
        return FlowTaskError(f"Task {tag} falhou: {type(exc).__name__}: {exc}")

    # ── condicionais e loops ───────────────────────────────────

    def _run_conditional(self, node: Node) -> None:
        result = self._evaluate(node.condition or "True")

        if result:
            taken, skipped = node.body_nodes, node.orelse_nodes
        else:
            taken, skipped = node.orelse_nodes, node.body_nodes

        for child in skipped:
            self._blocked.add(child)
        # o reset do ramo escolhido vem ANTES de executar: se fosse junto,
        # desfaria o bloqueio que um if/elif aninhado acabou de aplicar
        for child in taken:
            self._blocked.discard(child)
        for child in taken:
            self._run_node(child)

        self._executed.add(node.name)

    def _run_loop(self, node: Node) -> None:
        iteration = 0
        while self._evaluate(node.condition or "True"):
            if iteration >= MAX_LOOP_ITERATIONS:
                raise FlowError(
                    f"Loop '{node.name}' excedeu limite de {MAX_LOOP_ITERATIONS} iterações"
                )
            # cada iteração reavalia o corpo inteiro, inclusive ramos que a
            # iteração anterior tinha bloqueado — o reset é feito ANTES de
            # rodar o corpo, senão desfaria o bloqueio do próprio if
            for child in node.body_nodes:
                self._executed.discard(child)
                self._blocked.discard(child)
            for child in node.body_nodes:
                self._run_node(child)
            iteration += 1
        for child in node.body_nodes:
            self._executed.add(child)
        self._executed.add(node.name)

    def _evaluate(self, condition: str) -> bool:
        namespace = dict(self._globals)
        namespace["state"] = _EvalProxy(self._state.to_dict())
        try:
            return bool(eval(condition, namespace, {}))  # noqa: S307
        except Exception as exc:
            raise FlowConditionError(
                f"Falha ao avaliar condição {condition!r}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    # ── paralelismo ────────────────────────────────────────────

    def _run_parallel(self, node: Node) -> None:
        roots = node.body_roots or self._dag.roots_of(node.body_nodes)
        if not roots:
            self._executed.add(node.name)
            return

        base = self._state.to_dict()
        snapshots: list[State | None] = [None] * len(roots)
        errors: list[BaseException | None] = [None] * len(roots)

        def _branch(index: int, root: str) -> None:
            snap = self._state.copy()
            try:
                _set_state(snap)
                _Scheduler(
                    self._sub_dag(root, node), snap,
                    globals_ns=self._globals, tag=self._tag,
                ).run()
            except BaseException as exc:  # noqa: BLE001 - repassado ao caller
                errors[index] = exc
            snapshots[index] = snap

        threads = [
            threading.Thread(target=_branch, args=(i, root), daemon=True,
                             name=f"apex-{root}")
            for i, root in enumerate(roots)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        for exc in errors:
            if exc is not None:
                raise exc

        self._merge_states([s for s in snapshots if s is not None], base)
        for name in node.body_nodes:
            self._executed.add(name)
        self._executed.add(node.name)

    def _sub_dag(self, root: str, node: Node) -> DAG:
        """Subgrafo alcançável a partir de ``root`` dentro do bloco paralelo."""
        allowed = set(node.body_nodes)
        sub = DAG()
        stack = [root]
        seen: set[str] = set()

        while stack:
            current = stack.pop()
            if current in seen or current not in allowed:
                continue
            seen.add(current)
            sub.add_node(self._dag.nodes[current])
            for edge in self._dag.edges:
                if edge.source == current and edge.target in allowed:
                    sub.add_edge(edge.source, edge.target,
                                 edge.condition, edge.is_back_edge)
                    stack.append(edge.target)

        sub.entry = root
        return sub

    def _merge_states(self, snapshots: list[State], base: dict) -> None:
        """Aplica as escritas dos branches no state compartilhado.

        Política: last-write-wins na ordem dos branches (determinística, porque
        a ordem vem de ``body_roots``). Chaves escritas por mais de um branch
        geram um warning — nunca descarte silencioso.
        """
        changes = [self._changed_keys(base, snap.to_dict()) for snap in snapshots]

        writers: dict[str, int] = {}
        for change in changes:
            for key in change:
                writers[key] = writers.get(key, 0) + 1
        conflicts = sorted(k for k, n in writers.items() if n > 1)
        if conflicts:
            warnings.warn(
                "Parallel branches escreveram as mesmas chaves de state: "
                + ", ".join(repr(k) for k in conflicts)
                + ". O último branch (na ordem do corpo) vence.",
                stacklevel=2,
            )

        for change in changes:
            for key, value in change.items():
                self._state._data[key] = value

    @staticmethod
    def _changed_keys(base: dict, current: dict) -> dict:
        changed = {}
        for key, value in current.items():
            if key not in base:
                changed[key] = value
                continue
            try:
                if base[key] != value:
                    changed[key] = value
            except Exception:  # comparação customizada quebrada
                changed[key] = value
        return changed


def flow(func=None, *, name=None):
    """Decorador que transforma uma função em Flow.

    Uso:
        @flow
        def app():
            a()
            b()
    """
    if func is not None:
        return Flow(func, name=name or func.__name__)
    return lambda f: Flow(f, name=name or f.__name__)


def task(*, retry: int = 0, timeout: float = 0):
    """Configura metadados de uma task.

    Uso:
        @task(retry=3, timeout=30)
        def minha_task():
            ...
    """
    def decorator(fn):
        fn.__task_config__ = {
            "retry": retry,
            "timeout": timeout,
        }
        return fn
    return decorator


class _ParallelContext:
    """Context manager para execução paralela explícita.

    Uso:
        with parallel():
            search()
            docs()
            db()
    """
    __apex_parallel__ = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


parallel = _ParallelContext
