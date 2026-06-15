from __future__ import annotations

from ._dag import DAG


def ascii_tree(dag: DAG) -> str:
    """Gera árvore ASCII do DAG."""
    if not dag.nodes or not dag.entry:
        return "(empty)"

    tree = _TreeBuilder(dag)
    return tree.render()


def export_svg(dag: DAG, path: str) -> None:
    """Exporta DAG como SVG inline."""
    if not dag.nodes:
        return
    levels = dag._levels()
    node_names = set()
    for lvl in levels:
        for n in lvl:
            node_names.add(n)

    # layout simple: colunas por nível, linhas por posição no nível
    W, H = 120, 50
    PAD = 20
    rows: dict[str, tuple[int, int]] = {}
    for li, lvl in enumerate(levels):
        x = PAD + li * (W + PAD)
        y_start = PAD
        gap = max(0, (H * len(lvl)) // 2)
        for ni, name in enumerate(lvl):
            y = y_start + ni * (H + gap)
            rows[name] = (x, y)

    width = len(levels) * (W + PAD) + PAD
    height = max(coords[1] + H for coords in rows.values()) + PAD if rows else 200

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<style>',
        '  text { font-family: monospace; font-size: 12px; text-anchor: middle; }',
        '  .node rect { fill: #1a1a2e; stroke: #e94560; stroke-width: 2; rx: 6; }',
        '  .node text { fill: #eee; }',
        '  .edge { stroke: #555; stroke-width: 1.5; fill: none; marker-end: url(#arrow); }',
        '</style>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="7" refY="5"',
        '  markerWidth="6" markerHeight="6" orient="auto">',
        '  <path d="M0,0 L10,5 L0,10 Z" fill="#555"/></marker></defs>',
    ]

    for edge in dag.edges:
        if edge.is_back_edge:
            continue
        if edge.source in rows and edge.target in rows:
            sx, sy = rows[edge.source]
            tx, ty = rows[edge.target]
            parts.append(
                f'<line class="edge" x1="{sx + W}" y1="{sy + H//2}" '
                f'x2="{tx}" y2="{ty + H//2}"/>'
            )

    for name, node in dag.nodes.items():
        if name in rows:
            x, y = rows[name]
            parts = node.name.rsplit("_", 1)
            label = parts[0] if len(parts) == 2 and parts[1].isdigit() else node.name
            if node.kind == "conditional":
                label = f"? {node.condition[:12]}"
            elif node.kind == "loop":
                label = f"↻ {node.condition[:12]}"
            elif node.kind == "parallel":
                label = "[||]"
            parts.append(
                f'<g class="node">'
                f'<rect x="{x}" y="{y}" width="{W}" height="{H}"/>'
                f'<text x="{x + W//2}" y="{y + H//2 + 4}">{label[:16]}</text>'
                f'</g>'
            )

    parts.append('</svg>')
    with open(path, "w") as f:
        f.write("\n".join(parts))


class _TreeBuilder:
    def __init__(self, dag: DAG):
        self.dag = dag
        # adjacency tree: parent → list of children
        self._children: dict[str, list[str]] = {}
        for edge in dag.edges:
            if edge.is_back_edge:
                continue
            self._children.setdefault(edge.source, []).append(edge.target)
        self._visited: set[str] = set()
        self._lines: list[str] = []

    def render(self) -> str:
        if self.dag.entry in self.dag.nodes:
            self._walk(self.dag.entry, "", is_last=True, is_root=True)
        return "\n".join(self._lines)

    def _walk(self, name: str, prefix: str, is_last: bool, is_root: bool = False):
        if name in self._visited and not is_root:
            self._lines.append(f"{prefix}{'└── ' if is_last else '├── '}[{name}...]")
            return
        self._visited.add(name)

        node = self.dag.nodes.get(name)
        if node is None:
            self._lines.append(f"{prefix}{'└── ' if is_last else '├── '}{name}")
            return

        parts = node.name.rsplit("_", 1)
        label = parts[0] if len(parts) == 2 and parts[1].isdigit() else node.name

        # prefixos visuais
        if node.kind == "conditional":
            cond = node.condition or "?"
            display = f"? {cond}"
        elif node.kind == "loop":
            cond = node.condition or ""
            display = f"↻ {cond}"
        elif node.kind == "parallel":
            display = "[parallel]"
        else:
            display = label

        connector = "" if is_root else ("└── " if is_last else "├── ")
        self._lines.append(f"{prefix}{connector}{display}")

        children = self._children.get(name, [])
        child_prefix = prefix if is_root else (prefix + ("    " if is_last else "│   "))

        for i, child in enumerate(children):
            child_last = (i == len(children) - 1)
            self._walk(child, child_prefix, child_last)
