from __future__ import annotations

import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from typing import Any, Callable

from ._dag import DAG, Node, NodeConfig, build_dag
from ._state import State, _set_state, _get_state

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
        if isinstance(state, State):
            st = state
        else:
            data = dict(state or {})
            data.update(kwargs)
            st = State(data)

        _set_state(st)

        if not dag.nodes:
            self._func()
            return _get_state()

        scheduler = _Scheduler(dag, st)
        scheduler.run()

        return _get_state()

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
    def __init__(self, dag: DAG, state: State):
        self._dag = dag
        self._state = state
        self._executed: set[str] = set()
        self._blocked: set[str] = set()

    def run(self) -> None:
        levels = self._dag._levels()

        for level in levels:
            parallel_group = []
            for node_name in level:
                if node_name in self._executed or node_name in self._blocked:
                    continue
                node = self._dag.nodes[node_name]
                if node.kind == "conditional":
                    self._run_conditional(node)
                elif node.kind == "loop":
                    self._run_loop(node)
                elif node.kind == "parallel":
                    self._run_parallel(node)
                elif node.fn is not None:
                    parallel_group.append(node_name)

            if parallel_group:
                if len(parallel_group) == 1:
                    self._run_node(parallel_group[0])
                else:
                    self._run_parallel_group(parallel_group)

    def _run_node(self, node_name: str) -> None:
        if node_name in self._executed or node_name in self._blocked:
            return

        node = self._dag.nodes.get(node_name)
        if node is None or node.fn is None:
            self._executed.add(node_name)
            return

        config = node.config or NodeConfig()

        def _run():
            _set_state(self._state)
            try:
                if node.kind == "subflow":
                    return node.fn(state=self._state)
                return node.fn()
            finally:
                self._state = _get_state()

        last_exc = None
        return_value = None
        flow_tag = f"[{self._dag.entry}.{node_name}]"
        for attempt in range(config.retry + 1):
            try:
                if config.timeout > 0:
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(_run)
                        return_value = future.result(timeout=config.timeout)
                else:
                    return_value = _run()
                break
            except (FuturesTimeoutError, TimeoutError):
                msg = f"Task {flow_tag} excedeu timeout de {config.timeout}s"
                last_exc = TimeoutError(msg)
                if attempt == config.retry:
                    raise last_exc
                time.sleep(2 ** attempt)

            except Exception as e:
                last_exc = RuntimeError(
                    f"Task {flow_tag} falhou: {type(e).__name__}: {e}"
                )
                if attempt == config.retry:
                    raise last_exc
                time.sleep(2 ** attempt)

        if return_value is not None:
            name_key = node_name.rsplit("_", 1)[0] if node_name[-1].isdigit() else node_name
            self._state = _get_state()
            setattr(self._state, name_key, return_value)
            _set_state(self._state)

        self._executed.add(node_name)

    def _run_parallel_group(self, node_names: list[str]) -> None:
        with ThreadPoolExecutor(max_workers=len(node_names)) as executor:
            futures = {executor.submit(self._run_node, n): n for n in node_names}
            for future in as_completed(futures):
                future.result()

    def _run_conditional(self, node: Node) -> None:
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
            self._run_node(child)

        self._executed.add(node.name)

    def _run_loop(self, node: Node) -> None:
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
                self._run_node(child)
            iteration += 1
        for child in node.body_nodes:
            self._executed.add(child)
        self._executed.add(node.name)

    def _evaluate(self, condition: str) -> bool:
        import builtins as _blt
        st = self._state
        d = st.to_dict()
        ns = {"state": _EvalProxy(d), "__builtins__": _blt}
        try:
            return bool(eval(condition, ns, {}))
        except Exception as exc:
            if os.environ.get("PYRAM_DEBUG"):
                warnings.warn(
                    f"Condition eval failed: {condition!r} -> {type(exc).__name__}: {exc}"
                )
            return False

    def _run_parallel(self, node: Node) -> None:
        if node.body_nodes:
            with ThreadPoolExecutor(max_workers=len(node.body_nodes)) as executor:
                futures = {executor.submit(self._run_node, n): n for n in node.body_nodes}
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
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


parallel = _ParallelContext
