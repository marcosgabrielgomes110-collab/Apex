from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Literal


@dataclass
class NodeConfig:
    """Configuração opcional de task (decorator @task)."""
    retry: int = 0
    timeout: float = 0.0
    checkpoint: bool = False
    cache: bool = False


@dataclass
class Node:
    """Nó no DAG."""
    name: str
    kind: Literal["task", "conditional", "loop", "parallel", "subflow"]
    fn: Callable | None = None
    config: NodeConfig | None = None
    condition: str | None = None
    body_nodes: list[str] = field(default_factory=list)
    orelse_nodes: list[str] = field(default_factory=list)


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

        return levels


class _BuildContext:
    def __init__(self, func: Callable):
        self.func = func
        self.dag = DAG()
        self.counter: dict[str, int] = {}

    def unique_name(self, base: str) -> str:
        idx = self.counter.get(base, 0)
        name = base if idx == 0 else f"{base}_{idx}"
        self.counter[base] = idx + 1
        return name

    def resolve(self, name: str) -> Callable | None:
        for scope in [self.func.__globals__, getattr(self.func, '__globals__', {})]:
            if name in scope:
                return scope[name]
        return None

    def node_by_name(self, name: str) -> Node | None:
        return self.dag.nodes.get(name)


def build_dag(func: Callable) -> DAG:
    try:
        src = inspect.getsource(func)
    except OSError:
        raise TypeError(f"Não foi possível obter código fonte de {func.__name__}")

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

    last, _ = _walk_body(fn_def.body, ctx, parent=None)
    if dag.nodes:
        dag.entry = list(dag.nodes.keys())[0]

    return dag


def _walk_body(body: list[ast.stmt], ctx: _BuildContext,
               parent: str | None = None) -> tuple[str | None, list[str]]:
    """Percorre corpo do flow. Retorna (último_nó, todos_os_nós)."""
    last = parent
    all_nodes: list[str] = []
    for stmt in body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            last = _handle_call(stmt.value, ctx, last)
            if last:
                all_nodes.append(last)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
        elif isinstance(stmt, ast.If):
            last, branch_nodes = _handle_if(stmt, ctx, last)
            all_nodes.extend(branch_nodes)
        elif isinstance(stmt, ast.While):
            last, loop_nodes = _handle_while(stmt, ctx, last)
            all_nodes.extend(loop_nodes)
        elif isinstance(stmt, ast.With):
            last, with_nodes = _handle_with(stmt, ctx, last)
            all_nodes.extend(with_nodes)
        elif isinstance(stmt, ast.Assign):
            pass
        elif isinstance(stmt, (ast.Return, ast.Pass)):
            pass
    return last, all_nodes


def _handle_call(call: ast.Call, ctx: _BuildContext, last: str | None) -> str:
    name = _get_call_name(call)
    if name is None:
        return last

    fn = ctx.resolve(name)
    if fn is None:
        raise NameError(f"Task '{name}' não encontrada no escopo de {ctx.func.__name__}")

    # detecta se é subflow
    flow_dag = getattr(fn, '_flow_dag', None)
    kind: Literal["task", "conditional", "loop", "parallel", "subflow"] = "subflow" if flow_dag else "task"

    config = NodeConfig()
    tcfg = getattr(fn, '__task_config__', None)
    if tcfg:
        config = NodeConfig(
            retry=tcfg.get("retry", 0),
            timeout=tcfg.get("timeout", 0.0),
            checkpoint=tcfg.get("checkpoint", False),
            cache=tcfg.get("cache", False),
        )

    node_name = ctx.unique_name(name)
    node = Node(name=node_name, kind=kind, fn=fn, config=config)
    ctx.dag.add_node(node)

    if last and last in ctx.dag.nodes:
        ctx.dag.add_edge(last, node_name)

    return node_name


def _handle_if(stmt: ast.If, ctx: _BuildContext, last: str | None) -> tuple[str | None, list[str]]:
    cond_src = ast.unparse(stmt.test) if hasattr(ast, 'unparse') else _unparse_expr(stmt.test)

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
    cond_src = ast.unparse(stmt.test) if hasattr(ast, 'unparse') else _unparse_expr(stmt.test)

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
    is_parallel = False
    for item in stmt.items:
        c = item.context_expr
        if isinstance(c, ast.Call) and _get_call_name(c) == "parallel":
            is_parallel = True
            break

    if is_parallel:
        par_name = ctx.unique_name("parallel")
        par_node = Node(name=par_name, kind="parallel")
        ctx.dag.add_node(par_node)

        if last and last in ctx.dag.nodes:
            ctx.dag.add_edge(last, par_name)

        last_body, body_nodes = _walk_body(stmt.body, ctx, parent=par_name)
        if body_nodes:
            par_node.body_nodes = list(body_nodes)

        return par_name, [par_name] + par_node.body_nodes
    else:
        return _walk_body(stmt.body, ctx, parent=last)


def _get_call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return _unparse_expr(call.func)
    return None


def _unparse_expr(node: ast.AST) -> str:
    if hasattr(ast, 'unparse'):
        return ast.unparse(node)
    # fallback para Python < 3.9
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_unparse_expr(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        args = ", ".join(_unparse_expr(a) for a in node.args)
        return f"{_unparse_expr(node.func)}({args})"
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.BinOp):
        return f"{_unparse_expr(node.left)} {_binop_str(node.op)} {_unparse_expr(node.right)}"
    if isinstance(node, ast.Compare):
        parts = [_unparse_expr(node.left)]
        for op, comp in zip(node.ops, node.comparators):
            parts.append(_cmpop_str(op))
            parts.append(_unparse_expr(comp))
        return " ".join(parts)
    if isinstance(node, ast.UnaryOp):
        return f"{_unaryop_str(node.op)}{_unparse_expr(node.operand)}"
    if isinstance(node, ast.BoolOp):
        op = " and " if isinstance(node.op, ast.And) else " or "
        return op.join(_unparse_expr(v) for v in node.values)
    return "..."


def _binop_str(op: ast.operator) -> str:
    ops = {
        ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
        ast.Mod: "%", ast.Pow: "**", ast.FloorDiv: "//",
    }
    return ops.get(type(op), "?")


def _cmpop_str(op: ast.cmpop) -> str:
    ops = {
        ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=",
        ast.Gt: ">", ast.GtE: ">=", ast.Is: "is", ast.IsNot: "is not",
        ast.In: "in", ast.NotIn: "not in",
    }
    return ops.get(type(op), "?")


def _unaryop_str(op: ast.unaryop) -> str:
    ops = {ast.Not: "not ", ast.USub: "-", ast.UAdd: "+", ast.Invert: "~"}
    return ops.get(type(op), "")
