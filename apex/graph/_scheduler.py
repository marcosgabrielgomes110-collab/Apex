from __future__ import annotations

import inspect
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from ._dag import DAG, Node, NodeConfig, build_dag
from ._state import State, _set_state, _reset_state, _get_state

MAX_LOOP_ITERATIONS = 100


class CancelledError(RuntimeError):
    """Levantado quando a execução de um flow é cancelada cooperativamente."""


@dataclass
class RunResult:
    """Resultado detalhado de uma execução de flow.

    Atributos:
        state: estado final (ou parcial, em caso de erro/cancelamento).
        results: mapeamento nome-do-nó -> valor de retorno da task.
        duration: duração da execução em segundos.
        cancelled: True se o flow foi cancelado via cancel_event.
        errors: lista de exceções das falhas encontradas.
    """
    state: State
    results: dict = field(default_factory=dict)
    duration: float = 0.0
    cancelled: bool = False
    errors: list = field(default_factory=list)


class _EvalProxy:
    """Snapshot somente-leitura do state para avaliação de condições."""

    def __init__(self, data: dict):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        data = object.__getattribute__(self, "_data")
        if name not in data:
            raise AttributeError(f"State key '{name}' not found")
        val = data[name]
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
        self._dag_lock = threading.Lock()
        self._flow_dag = True

    def _ensure_dag(self) -> DAG:
        if self._dag is None:
            with self._dag_lock:
                if self._dag is None:
                    self._dag = build_dag(self._func)
        return self._dag

    def run(self, state: dict | None = None, *, cancel_event=None, **kwargs) -> State:
        """Executa o flow e retorna o State final.

        `cancel_event` (threading.Event, opcional) permite cancelamento
        cooperativo: é verificado antes de iniciar cada nó; se estiver setado,
        levanta CancelledError.
        """
        result = self._execute(state, cancel_event, kwargs)
        if result.cancelled:
            raise CancelledError("Execução do flow cancelada")
        if result.errors:
            raise result.errors[0]
        return result.state

    def run_detailed(self, state: dict | None = None, *, cancel_event=None, **kwargs) -> RunResult:
        """Executa o flow e retorna um RunResult (sem levantar em erro/cancel).

        Falhas de task são coletadas em `RunResult.errors`; cancelamento é
        reportado em `RunResult.cancelled` em vez de levantar exceção.
        """
        return self._execute(state, cancel_event, kwargs)

    def _execute(self, state, cancel_event, kwargs) -> RunResult:
        if inspect.iscoroutinefunction(self._func):
            raise TypeError(
                f"async def não suportado; use def síncrono: '{self._func.__name__}'"
            )
        t0 = time.monotonic()
        dag = self._ensure_dag()
        if isinstance(state, State):
            st = state
        else:
            data = dict(state or {})
            data.update(kwargs)
            st = State(data)

        token = _set_state(st)
        scheduler = _Scheduler(dag, st, cancel_event=cancel_event)
        result = RunResult(state=st)

        try:
            if cancel_event is not None and cancel_event.is_set():
                raise CancelledError("Execução do flow cancelada")
            if not dag.nodes:
                self._func()
            else:
                scheduler.run()
        except CancelledError:
            result.cancelled = True
        except Exception as e:
            result.errors.append(e)
        finally:
            result.state = _get_state()
            result.results = dict(scheduler._results)
            result.duration = time.monotonic() - t0
            _reset_state(token)

        return result

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
    def __init__(self, dag: DAG, state: State, cancel_event=None):
        self._dag = dag
        self._state = state
        self._executed: set[str] = set()
        self._blocked: set[str] = set()
        self._cancel_event = cancel_event
        self._results: dict[str, Any] = {}

    def _check_cancel(self) -> None:
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise CancelledError("Execução do flow cancelada")

    def run(self) -> None:
        levels = self._dag._levels()

        for level in levels:
            self._check_cancel()
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

    def _run_by_name(self, node_name: str) -> None:
        self._check_cancel()
        if node_name in self._executed or node_name in self._blocked:
            return
        node = self._dag.nodes.get(node_name)
        if node is None:
            return
        if node.kind == "conditional":
            self._run_conditional(node)
        elif node.kind == "loop":
            self._run_loop(node)
        elif node.kind == "parallel":
            self._run_parallel(node)
        elif node.fn is not None:
            self._run_node(node_name)
        else:
            self._executed.add(node_name)

    def _run_node(self, node_name: str, state: State | None = None) -> None:
        if node_name in self._executed or node_name in self._blocked:
            return

        node = self._dag.nodes.get(node_name)
        if node is None or node.fn is None:
            self._executed.add(node_name)
            return

        target = state if state is not None else self._state
        config = node.config or NodeConfig()
        flow_tag = f"[{self._dag.entry}.{node_name}]"

        def _invoke(st: State):
            _set_state(st)
            if node.kind == "subflow":
                return node.fn(state=st)
            return node.fn()

        return_value = None
        for attempt in range(config.retry + 1):
            try:
                if config.timeout > 0:
                    return_value = self._run_timed(_invoke, target, config.timeout, flow_tag)
                else:
                    return_value = _invoke(target)
                break
            except TimeoutError:
                if attempt == config.retry:
                    raise
                time.sleep(min(2 ** attempt, 60))
            except Exception as e:
                if attempt == config.retry:
                    raise RuntimeError(
                        f"Task {flow_tag} falhou: {type(e).__name__}: {e}"
                    ) from e
                time.sleep(min(2 ** attempt, 60))

        if return_value is not None and node.fn is not None and node.kind != "subflow":
            func_name = node.name
            if func_name in target:
                warnings.warn(
                    f"Retorno da task '{func_name}' sobrescreveu chave de estado "
                    f"pré-existente com o mesmo nome",
                    RuntimeWarning,
                    stacklevel=2,
                )
            setattr(target, func_name, return_value)

        self._results[node_name] = return_value
        self._executed.add(node_name)

    def _run_timed(self, invoke, target: State, timeout: float, flow_tag: str):
        snapshot = target.copy()
        holder: dict = {}

        def _run():
            _set_state(snapshot)
            try:
                holder["result"] = invoke(snapshot)
            except BaseException as e:
                holder["error"] = e

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            raise TimeoutError(f"Task {flow_tag} excedeu timeout de {timeout}s")
        if "error" in holder:
            raise holder["error"]
        self._merge_single(target, snapshot)
        return holder.get("result")

    def _merge_single(self, target: State, snapshot: State) -> None:
        tgt = object.__getattribute__(target, "_data")
        snap = object.__getattribute__(snapshot, "_data")
        tgt.clear()
        tgt.update(snap)

    def _run_isolated(self, node_name: str, snapshot: State) -> State:
        self._run_node(node_name, state=snapshot)
        return snapshot

    def _merge_snapshots(self, snapshots: list[State]) -> None:
        baseline = self._state.to_dict()
        writers: dict[str, list] = {}
        for snap in snapshots:
            for k, v in snap.to_dict().items():
                if k in baseline and baseline[k] == v:
                    continue
                writers.setdefault(k, []).append(v)
        for k, values in writers.items():
            distinct: list = []
            for v in values:
                if v not in distinct:
                    distinct.append(v)
            if len(distinct) > 1:
                shown = ", ".join(repr(v) for v in distinct)
                raise RuntimeError(
                    f"Conflito de escrita paralela na chave '{k}': "
                    f"múltiplas tasks escreveram valores diferentes: {shown}"
                )
            setattr(self._state, k, distinct[0])

    def _run_parallel_group(self, node_names: list[str]) -> None:
        snapshots: list[State] = []
        lock = threading.Lock()

        def _run_and_store(node_name):
            snap = self._state.copy()
            result = self._run_isolated(node_name, snap)
            with lock:
                snapshots.append(result)

        with ThreadPoolExecutor(max_workers=len(node_names)) as executor:
            futures = [executor.submit(_run_and_store, n) for n in node_names]
            for future in as_completed(futures):
                future.result()

        self._merge_snapshots(snapshots)

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
            self._run_by_name(child)

        self._executed.add(node.name)

    def _run_loop(self, node: Node) -> None:
        iteration = 0
        while self._evaluate(node.condition or "True"):
            self._check_cancel()
            if iteration >= MAX_LOOP_ITERATIONS:
                raise RuntimeError(
                    f"Loop '{node.name}' excedeu limite de {MAX_LOOP_ITERATIONS} iterações"
                )
            for child in node.body_nodes:
                self._executed.discard(child)
                self._blocked.discard(child)
            for child in node.body_nodes:
                self._run_by_name(child)
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
            raise RuntimeError(
                f"Falha ao avaliar condição '{condition}': "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def _run_parallel(self, node: Node) -> None:
        if node.body_nodes:
            snapshots: list[State] = []
            lock = threading.Lock()

            def _run_and_store(node_name):
                snap = self._state.copy()
                result = self._run_isolated(node_name, snap)
                with lock:
                    snapshots.append(result)

            with ThreadPoolExecutor(max_workers=len(node.body_nodes)) as executor:
                futures = [executor.submit(_run_and_store, n) for n in node.body_nodes]
                for future in as_completed(futures):
                    future.result()

            self._merge_snapshots(snapshots)

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
