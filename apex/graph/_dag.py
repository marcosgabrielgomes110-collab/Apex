from __future__ import annotations

import ast
import builtins as _builtins
import inspect
import textwrap
from dataclasses import dataclass, field
from typing import Callable, Literal

from ._state import state as _state_proxy

MAX_LABEL = 40


@dataclass
class NodeConfig:
    """Configuração opcional de task (decorator @task)."""
    retry: int = 0
    timeout: float = 0.0


@dataclass
class Node:
    """Nó no DAG."""
    name: str
    kind: Literal["task", "conditional", "loop", "parallel", "subflow", "inline"]
    fn: Callable | None = None
    config: NodeConfig | None = None
    condition: str | None = None
    body_nodes: list[str] = field(default_factory=list)
    body_roots: list[str] = field(default_factory=list)
    orelse_nodes: list[str] = field(default_factory=list)
    assign_to: str | None = None
    arg_builder: Callable | None = None


@dataclass
class Edge:
    """Aresta direcionada."""
    source: str
    target: str
    condition: str | None = None
    is_back_edge: bool = False


@dataclass
class DAG:
    """Grafo direcionado."""
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    entry: str = ""

    def add_node(self, node: Node) -> None:
        self.nodes[node.name] = node

    def add_edge(self, source: str, target: str,
                 condition: str | None = None,
                 is_back_edge: bool = False) -> None:
        self.edges.append(Edge(source=source, target=target,
                               condition=condition, is_back_edge=is_back_edge))

    def roots_of(self, names: list[str]) -> list[str]:
        """Nós da lista que não dependem de outro nó da mesma lista.

        Back-edges de loop são ignoradas: um `while` dentro do bloco é raiz,
        mesmo recebendo a aresta de retorno do próprio corpo.
        """
        scope = set(names)
        return [
            n for n in names
            if not any(
                not e.is_back_edge and e.source in scope and e.target == n
                for e in self.edges
            )
        ]

    def _levels(self) -> list[list[str]]:
        """Kahn topological sort agrupado em níveis paralelizáveis."""
        in_degree: dict[str, int] = {n: 0 for n in self.nodes}
        adj: dict[str, list[str]] = {n: [] for n in self.nodes}

        for edge in self.edges:
            if edge.is_back_edge:
                continue
            adj[edge.source].append(edge.target)
            in_degree[edge.target] += 1

        levels = []
        queue = [n for n, d in in_degree.items() if d == 0]

        while queue:
            levels.append(list(queue))
            next_queue = []
            for node in queue:
                for neighbor in adj[node]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            queue = next_queue

        remaining = [n for n in in_degree if in_degree[n] > 0]
        if remaining:
            raise ValueError(
                "Cycle detected in flow! Nodes still with dependencies: "
                + ", ".join(sorted(remaining))
            )

        return levels


class _BuildContext:
    def __init__(self, func: Callable):
        self.func = func
        self.dag = DAG()
        self.counter: dict[str, int] = {}
        # funções definidas dentro do corpo do flow (def aninhado)
        self.locals: dict[str, Callable] = {}
        self.local_ns: dict = dict(getattr(func, "__globals__", {}))
        # variáveis do escopo que envolve o flow entram no namespace dos nós
        # inline (senão `svc.metodo()` com `svc` de closure não resolve)
        closure = getattr(func, "__closure__", None)
        code = getattr(func, "__code__", None)
        if closure and code:
            for cell, var in zip(closure, code.co_freevars):
                try:
                    self.local_ns[var] = cell.cell_contents
                except ValueError:
                    continue
        self.local_ns["state"] = _state_proxy

    def unique_name(self, base: str) -> str:
        idx = self.counter.get(base, 0)
        name = base if idx == 0 else f"{base}_{idx}"
        self.counter[base] = idx + 1
        return name

    def register_local(self, fn_def: ast.FunctionDef) -> None:
        module = ast.Module(body=[fn_def], type_ignores=[])
        ast.fix_missing_locations(module)
        code = compile(module, "<apex-flow-local>", "exec")
        exec(code, self.local_ns)  # noqa: S102 - código do próprio usuário
        self.locals[fn_def.name] = self.local_ns[fn_def.name]

    def resolve(self, name: str) -> Callable | None:
        if name in self.locals:
            return self.locals[name]
        scope = getattr(self.func, '__globals__', {})
        if name in scope:
            return scope[name]
        closure = getattr(self.func, '__closure__', None)
        code = getattr(self.func, '__code__', None)
        if closure and code:
            freevars = code.co_freevars
            for cell, var in zip(closure, freevars):
                if var == name:
                    try:
                        return cell.cell_contents
                    except ValueError:
                        return None
        return None


def build_dag(func: Callable) -> DAG:
    try:
        src = inspect.getsource(func)
    except OSError:
        raise TypeError(
            f"Não foi possível obter o código fonte de '{func.__name__}'. "
            "Flows precisam estar em um arquivo .py importável "
            "(REPL, exec() e notebooks sem arquivo não são suportados)."
        )

    src = textwrap.dedent(src)
    tree = ast.parse(src)
    fn_def = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_def = node
            break
    if fn_def is None:
        raise TypeError(f"Não foi possível encontrar definição de função em {func.__name__}")

    ctx = _BuildContext(func)
    dag = ctx.dag

    _walk_body(fn_def.body, ctx, parent=None)
    if dag.nodes:
        # entry = nó com in-degree 0 (verdadeira raiz do DAG)
        indeg = {n: 0 for n in dag.nodes}
        for e in dag.edges:
            if not e.is_back_edge:
                indeg[e.target] = indeg.get(e.target, 0) + 1
        roots = [n for n, d in indeg.items() if d == 0]
        dag.entry = roots[0] if roots else list(dag.nodes.keys())[0]

    return dag


def _walk_body(body: list[ast.stmt], ctx: _BuildContext,
               parent: str | None = None,
               chain: bool = True) -> tuple[str | None, list[str]]:
    """Percorre corpo do flow. Retorna (último_nó, todos_os_nós).

    Com ``chain=False`` cada statement do corpo parte de ``parent`` em vez de
    encadear no anterior — é o que dá semântica de fork ao `with parallel()`.
    """
    last = parent
    all_nodes: list[str] = []
    for stmt in body:
        anchor = last if chain else parent
        if isinstance(stmt, ast.FunctionDef):
            ctx.register_local(stmt)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            node = _handle_call(stmt.value, ctx, anchor)
            if node:
                last = node
                all_nodes.append(node)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
        elif isinstance(stmt, ast.If):
            last, branch_nodes = _handle_if(stmt, ctx, anchor)
            all_nodes.extend(branch_nodes)
        elif isinstance(stmt, ast.While):
            last, loop_nodes = _handle_while(stmt, ctx, anchor)
            all_nodes.extend(loop_nodes)
        elif isinstance(stmt, ast.With):
            last, with_nodes = _handle_with(stmt, ctx, anchor)
            all_nodes.extend(with_nodes)
        elif isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            assigned = _handle_assign(stmt, ctx, anchor)
            if assigned:
                last = assigned
                all_nodes.append(assigned)
        elif isinstance(stmt, (ast.Return, ast.Pass)):
            pass
    return (last if chain else parent), all_nodes


def _handle_call(call: ast.Call, ctx: _BuildContext,
                 parent: str | None, assign_to: str | None = None) -> str | None:
    fn: Callable | None = None
    inline = False

    if isinstance(call.func, ast.Name):
        name = call.func.id
        resolved = ctx.resolve(name)
        if resolved is None:
            if hasattr(_builtins, name):
                inline = True          # print(), len(), range()...
            else:
                raise NameError(
                    f"Task '{name}' not found in scope of flow '{ctx.func.__name__}'. "
                    f"Ensure the function is defined at module level or in an enclosing scope."
                )
        elif not callable(resolved):
            raise TypeError(
                f"'{name}' is not callable (found {type(resolved).__name__}) "
                f"in flow '{ctx.func.__name__}'."
            )
        else:
            fn = resolved
    else:
        # obj.metodo(...), chamada de lambda, subscript... resolve em runtime
        inline = True

    arg_builder = None
    if inline:
        return _handle_inline_expr(call, ctx, parent, assign_to)

    kind: Literal["task", "conditional", "loop", "parallel", "subflow", "inline"]
    kind = "subflow" if getattr(fn, "_flow_dag", False) else "task"
    node_name = ctx.unique_name(call.func.id)
    if call.args or call.keywords:
        if kind == "subflow":
            raise TypeError(
                f"Subflow '{name}' não aceita argumentos — "
                f"passe dados via state."
            )
        arg_builder = _make_arg_builder(call, ctx)

    config = NodeConfig()
    tcfg = getattr(fn, '__task_config__', None)
    if tcfg:
        config = NodeConfig(
            retry=tcfg.get("retry", 0),
            timeout=tcfg.get("timeout", 0.0),
        )

    node = Node(name=node_name, kind=kind, fn=fn, config=config,
                assign_to=assign_to, arg_builder=arg_builder)
    ctx.dag.add_node(node)

    if parent and parent in ctx.dag.nodes:
        ctx.dag.add_edge(parent, node_name)

    return node_name


def _handle_assign(stmt: ast.stmt, ctx: _BuildContext,
                   parent: str | None) -> str | None:
    """Atribuições no corpo do flow viram nós executáveis.

    ``x = task()`` vira nó de task com o retorno gravado em ``state.x``.
    Qualquer outra atribuição (``state.x = ...``, ``state.x += 1``, ``del``)
    vira nó inline executado na ordem do DAG — antes era silenciosamente
    ignorado.
    """
    if (isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)):
        target = stmt.targets[0].id
        if isinstance(stmt.value, ast.Call):
            return _handle_call(stmt.value, ctx, parent, assign_to=target)
        return _handle_inline_expr(stmt.value, ctx, parent, assign_to=target)
    return _handle_inline_stmt(stmt, ctx, parent)


def _handle_if(stmt: ast.If, ctx: _BuildContext, last: str | None) -> tuple[str | None, list[str]]:
    cond_src = ast.unparse(stmt.test)

    cond_name = ctx.unique_name("if")
    cond_node = Node(name=cond_name, kind="conditional", condition=cond_src)
    ctx.dag.add_node(cond_node)

    if last and last in ctx.dag.nodes:
        ctx.dag.add_edge(last, cond_name)

    all_nodes: list[str] = [cond_name]

    last_body, body_nodes = _walk_body(stmt.body, ctx, parent=cond_name)
    if body_nodes:
        cond_node.body_nodes = list(body_nodes)
    all_nodes.extend(cond_node.body_nodes)

    if stmt.orelse:
        last_else, else_nodes = _walk_body(stmt.orelse, ctx, parent=cond_name)
        if else_nodes:
            cond_node.orelse_nodes = list(else_nodes)
        all_nodes.extend(cond_node.orelse_nodes)

    # merge implícito
    merge_name = ctx.unique_name("merge")
    merge_node = Node(name=merge_name, kind="task", fn=None)
    ctx.dag.add_node(merge_node)

    if last_body and last_body in ctx.dag.nodes:
        ctx.dag.add_edge(last_body, merge_name)
    else:
        ctx.dag.add_edge(cond_name, merge_name)

    if stmt.orelse and last_else and last_else in ctx.dag.nodes:
        ctx.dag.add_edge(last_else, merge_name)
    elif stmt.orelse:
        ctx.dag.add_edge(cond_name, merge_name)

    all_nodes.append(merge_name)
    return merge_name, all_nodes


def _handle_while(stmt: ast.While, ctx: _BuildContext, last: str | None) -> tuple[str | None, list[str]]:
    cond_src = ast.unparse(stmt.test)

    loop_name = ctx.unique_name("loop")
    loop_node = Node(name=loop_name, kind="loop", condition=cond_src)
    ctx.dag.add_node(loop_node)

    if last and last in ctx.dag.nodes:
        ctx.dag.add_edge(last, loop_name)

    last_body, body_nodes = _walk_body(stmt.body, ctx, parent=loop_name)
    if body_nodes:
        loop_node.body_nodes = list(body_nodes)

    if last_body and last_body in ctx.dag.nodes:
        # back-edge do fim do corpo para o loop
        ctx.dag.add_edge(last_body, loop_name, condition="loop", is_back_edge=True)

    all_nodes = [loop_name] + loop_node.body_nodes
    return loop_name, all_nodes


def _handle_with(stmt: ast.With, ctx: _BuildContext, last: str | None) -> tuple[str | None, list[str]]:
    is_parallel = any(_is_parallel_ctx(item.context_expr, ctx) for item in stmt.items)

    if is_parallel:
        par_name = ctx.unique_name("parallel")
        par_node = Node(name=par_name, kind="parallel")
        ctx.dag.add_node(par_node)

        if last and last in ctx.dag.nodes:
            ctx.dag.add_edge(last, par_name)

        # corpo sem encadeamento: cada statement é um branch independente
        _, body_nodes = _walk_body(stmt.body, ctx, parent=par_name, chain=False)
        if body_nodes:
            par_node.body_nodes = list(body_nodes)
            par_node.body_roots = ctx.dag.roots_of(list(body_nodes))

        return par_name, [par_name] + par_node.body_nodes
    else:
        return _walk_body(stmt.body, ctx, parent=last)


def _is_parallel_ctx(expr: ast.expr, ctx: _BuildContext) -> bool:
    if not isinstance(expr, ast.Call):
        return False
    name = _get_call_name(expr)
    if name is None:
        return False
    obj = ctx.resolve(name)
    if obj is not None:
        return bool(getattr(obj, "__apex_parallel__", False))
    return name == "parallel"


def _handle_inline_expr(expr: ast.expr, ctx: _BuildContext, parent: str | None,
                        assign_to: str | None = None) -> str:
    """Nó que avalia uma expressão avulsa no ponto do DAG."""
    code = _compile_expr(expr)
    namespace = ctx.local_ns

    def _run():
        return eval(code, namespace)  # código do próprio usuário

    _run.__name__ = _inline_label(expr)
    node_name = ctx.unique_name(_run.__name__)
    ctx.dag.add_node(Node(name=node_name, kind="inline", fn=_run,
                          assign_to=assign_to))

    if parent and parent in ctx.dag.nodes:
        ctx.dag.add_edge(parent, node_name)

    return node_name


def _make_arg_builder(call: ast.Call, ctx: _BuildContext) -> Callable:
    """Avalia os argumentos da chamada na hora da execução do nó."""
    positional = [_compile_expr(arg) for arg in call.args]
    named = [(kw.arg, _compile_expr(kw.value)) for kw in call.keywords]
    namespace = ctx.local_ns

    def _build() -> tuple[list, dict]:
        args = [eval(code, namespace) for code in positional]  # noqa: S307
        kwargs: dict = {}
        for key, code in named:
            value = eval(code, namespace)  # noqa: S307
            if key is None:
                kwargs.update(value)
            else:
                kwargs[key] = value
        return args, kwargs

    return _build


def _compile_expr(node: ast.expr):
    expression = ast.Expression(body=node)
    ast.fix_missing_locations(expression)
    return compile(expression, "<apex-arg>", "eval")


def _handle_inline_stmt(stmt: ast.stmt, ctx: _BuildContext,
                        parent: str | None) -> str | None:
    module = ast.Module(body=[stmt], type_ignores=[])
    ast.fix_missing_locations(module)
    code = compile(module, "<apex-inline>", "exec")
    namespace = ctx.local_ns

    def _run():
        exec(code, namespace)  # noqa: S102 - código do próprio usuário

    _run.__name__ = _inline_label(stmt)
    node_name = ctx.unique_name(_run.__name__)
    ctx.dag.add_node(Node(name=node_name, kind="inline", fn=_run))

    if parent and parent in ctx.dag.nodes:
        ctx.dag.add_edge(parent, node_name)

    return node_name


def _inline_label(node: ast.AST) -> str:
    label = " ".join(ast.unparse(node).split())
    if len(label) > MAX_LABEL:
        label = label[: MAX_LABEL - 1] + "…"
    return label


def _get_call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return ast.unparse(call.func)
    return None
