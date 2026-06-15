from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import Any, Callable

from ._dag import DAG, Node, NodeConfig, build_dag
from ._state import State, _set_state, _get_state
from ._checkpoint import CheckpointManager

MAX_LOOP_ITERATIONS = 100


class _EvalProxy:
    """Snapshot somente-leitura do state para avaliação de condições."""

    def __init__(self, data: dict):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        val = object.__getattribute__(self, "_data").get(name)
        if isinstance(val, dict):
            return _EvalProxy(val)
        return val

    def __bool__(self) -> bool:
        return bool(object.__getattribute__(self, "_data"))


class Flow:
    """Workflow executável. Criado pelo decorator @flow."""

    def __init__(self, func: Callable, *, name: str = ""):
        self._func = func
        self._name = name or func.__name__
        self._dag: DAG | None = None
        func._flow_dag = True

    def _ensure_dag(self) -> DAG:
        if self._dag is None:
            self._dag = build_dag(self._func)
        return self._dag

    def run(self, state: dict | None = None, **kwargs) -> State:
        dag = self._ensure_dag()
        if not dag.nodes:
            st = State(state or {})
            _set_state(st)
            self._func()
            return _get_state()

        st = State(state or {})
        _set_state(st)

        cpm = CheckpointManager(self._name)
        scheduler = _Scheduler(dag, st, cpm, self._name)
        scheduler.run()

        return _get_state()

    def viz(self, fmt: str = "ascii") -> str:
        from ._viz import ascii_tree
        return ascii_tree(self._ensure_dag())

    def viz_svg(self, path: str) -> None:
        from ._viz import export_svg
        export_svg(self._ensure_dag(), path)

    def map(self) -> DAG:
        return self._ensure_dag()

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def __repr__(self) -> str:
        return f"Flow({self._name!r})"


class _Scheduler:
    def __init__(self, dag: DAG, state: State, cpm: CheckpointManager, flow_name: str):
        self._dag = dag
        self._state = state
        self._cpm = cpm
        self._flow_name = flow_name
        self._executed: set[str] = set()
        self._blocked: set[str] = set()

    def run(self) -> None:
        manifest = self._cpm.load_manifest()
        levels = self._dag._levels()

        for level in levels:
            parallel_group = []
            for node_name in level:
                if node_name in self._executed or node_name in self._blocked:
                    continue
                node = self._dag.nodes[node_name]
                if node.kind == "conditional":
                    self._run_conditional(node, manifest)
                elif node.kind == "loop":
                    self._run_loop(node, manifest)
                elif node.kind == "parallel":
                    self._run_parallel(node, manifest)
                elif node.fn is not None:
                    parallel_group.append(node_name)

            if parallel_group:
                if len(parallel_group) == 1:
                    self._run_node(parallel_group[0], manifest)
                else:
                    self._run_parallel_group(parallel_group, manifest)

    def _run_node(self, node_name: str, manifest: list[str]) -> None:
        if node_name in self._executed or node_name in self._blocked:
            return

        node = self._dag.nodes.get(node_name)
        if node is None or node.fn is None:
            self._executed.add(node_name)
            return

        if node_name in manifest:
            self._executed.add(node_name)
            return

        config = node.config or NodeConfig()

        if config.checkpoint:
            saved = self._cpm.load(node_name)
            if saved:
                st = State.from_dict(saved)
                _set_state(st)
                self._state = st
                manifest.append(node_name)
                self._cpm.save_manifest(manifest)
                self._executed.add(node_name)
                return

        if config.cache:
            cached = self._cpm.cache_get(node_name, self._state.to_dict())
            if cached is not None:
                self._executed.add(node_name)
                return

        last_exc = None
        for attempt in range(config.retry + 1):
            try:
                _set_state(self._state)
                result = node.fn()
                self._state = _get_state()
                break
            except (FuturesTimeoutError, TimeoutError):
                last_exc = TimeoutError(f"Task '{node_name}' excedeu timeout de {config.timeout}s")
                if attempt == config.retry:
                    raise last_exc
                time.sleep(2 ** attempt)
            except Exception as e:
                last_exc = e
                if attempt == config.retry:
                    raise
                time.sleep(2 ** attempt)

        self._executed.add(node_name)

        if config.checkpoint:
            self._cpm.save(node_name, self._state.to_dict())
            manifest.append(node_name)
            self._cpm.save_manifest(manifest)

        if config.cache:
            self._cpm.cache_set(node_name, self._state.to_dict(), True)

    def _run_parallel_group(self, node_names: list[str], manifest: list[str]) -> None:
        with ThreadPoolExecutor(max_workers=len(node_names)) as executor:
            futures = {executor.submit(self._run_node, n, manifest): n for n in node_names}
            for future in as_completed(futures):
                future.result()

    def _run_conditional(self, node: Node, manifest: list[str]) -> None:
        cond = node.condition or "True"
        result = self._evaluate(cond)

        if result:
            taken = node.body_nodes
            skipped = node.orelse_nodes
        else:
            taken = node.orelse_nodes
            skipped = node.body_nodes

        for child in skipped:
            self._blocked.add(child)
        for child in taken:
            self._run_node(child, manifest)

        self._executed.add(node.name)

    def _run_loop(self, node: Node, manifest: list[str]) -> None:
        iteration = 0
        while self._evaluate(node.condition or "True"):
            if iteration >= MAX_LOOP_ITERATIONS:
                raise RuntimeError(
                    f"Loop '{node.name}' excedeu limite de {MAX_LOOP_ITERATIONS} iterações"
                )
            for child in node.body_nodes:
                if child in self._blocked:
                    continue
                self._executed.discard(child)
                self._run_node(child, manifest)
                self._executed.discard(child)
            iteration += 1
        # mantém body nodes como executados para o scheduler topológico não re-executar
        for child in node.body_nodes:
            self._executed.add(child)
        self._executed.add(node.name)

    def _evaluate(self, condition: str) -> bool:
        import builtins as _blt
        st = self._state
        d = st.to_dict()
        # snapshot somente-leitura — evita que eval dispare __getattr__ e crie atributos
        ns = {"state": _EvalProxy(d), "__builtins__": _blt}
        try:
            return bool(eval(condition, ns, {}))
        except Exception:
            return False

    def _run_parallel(self, node: Node, manifest: list[str]) -> None:
        if node.body_nodes:
            with ThreadPoolExecutor(max_workers=len(node.body_nodes)) as executor:
                futures = {executor.submit(self._run_node, n, manifest): n for n in node.body_nodes}
                for future in as_completed(futures):
                    future.result()
        self._executed.add(node.name)


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


def task(*, retry: int = 0, timeout: float = 0, checkpoint: bool = False, cache: bool = False):
    """Configura metadados de uma task.

    Uso:
        @task(retry=3, timeout=30, checkpoint=True, cache=True)
        def minha_task():
            ...
    """
    def decorator(fn):
        fn.__task_config__ = {
            "retry": retry,
            "timeout": timeout,
            "checkpoint": checkpoint,
            "cache": cache,
        }
        return fn
    return decorator


def parallel():
    """Context manager para execução paralela explícita.

    Uso:
        with parallel():
            search()
            docs()
            db()
    """
    from contextlib import contextmanager
    @contextmanager
    def _ctx():
        yield
    return _ctx()
