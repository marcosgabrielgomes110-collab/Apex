from __future__ import annotations

from ._dag import DAG

NODE_W, NODE_H = 140, 50
PAD = 40
LEVEL_GAP = 60
ROW_GAP = 24


def _label(node):
    if node.fn and hasattr(node.fn, '__name__'):
        label = node.fn.__name__
    else:
        label = node.name.rsplit("_", 1)[0] if "_" in node.name else node.name
    if node.kind == "conditional":
        return f"? {node.condition or ''}"
    elif node.kind == "loop":
        return f"↻ {node.condition or ''}"
    elif node.kind == "parallel":
        return "║ parallel ║"
    return label


def _layout_grid(dag: DAG):
    levels = dag._levels()
    positions: dict[str, tuple[float, float]] = {}
    for li, lvl in enumerate(levels):
        x = PAD + li * (NODE_W + LEVEL_GAP)
        n = len(lvl)
        total_h = n * NODE_H + (n - 1) * ROW_GAP
        y_start = PAD + (max(0, 200 - total_h)) // 2 if n <= 3 else PAD
        for ni, name in enumerate(lvl):
            positions[name] = (x, y_start + ni * (NODE_H + ROW_GAP))
    w = (len(levels) * (NODE_W + LEVEL_GAP) + PAD) if positions else 200
    h = max(y + NODE_H for _, y in positions.values()) + PAD if positions else 200
    return levels, positions, int(w), int(h)


def _node_kind_style(kind: str) -> dict:
    styles = {
        "task": {"fill": "#1a1a2e", "stroke": "#e94560", "rx": "6"},
        "conditional": {"fill": "#1a1a2e", "stroke": "#f5a623", "rx": "0"},
        "loop": {"fill": "#1a1a2e", "stroke": "#4ecdc4", "rx": "12"},
        "parallel": {"fill": "#1a1a2e", "stroke": "#a855f7", "rx": "6", "stroke-dasharray": "4"},
        "subflow": {"fill": "#16213e", "stroke": "#0f3460", "rx": "6"},
    }
    return styles.get(kind, styles["task"])


# ── ASCII ──────────────────────────────────────────────────────


def ascii_tree(dag: DAG) -> str:
    if not dag.nodes or not dag.entry:
        return "(empty)"
    return _TreeBuilder(dag).render()


def export_ascii(dag: DAG) -> str:
    return ascii_tree(dag)


# ── SVG ────────────────────────────────────────────────────────


def export_svg(dag: DAG, path: str | None = None) -> str:
    if not dag.nodes:
        return ""
    levels, positions, width, height = _layout_grid(dag)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        "<style>",
        "  text { font-family: monospace; font-size: 12px; text-anchor: middle; dominant-baseline: central; }",
        "  .edge { stroke: #555; stroke-width: 1.5; fill: none; }",
        "  .edge-back { stroke: #888; stroke-width: 1; stroke-dasharray: 4,3; fill: none; }",
        "</style>",
    ]

    for edge in dag.edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        sx, sy = positions[edge.source]
        tx, ty = positions[edge.target]
        x1, y1 = sx + NODE_W, sy + NODE_H // 2
        x2, y2 = tx, ty + NODE_H // 2
        cls = "edge-back" if edge.is_back_edge else "edge"
        if edge.is_back_edge:
            lines.append(
                f'<path class="{cls}" d="M{x1},{y1} C{x1 + 40},{y1} {x2 - 40},{y2} {x2},{y2}" '
                f'marker-end="url(#arrow)"/>'
            )
        else:
            lines.append(
                f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                f'marker-end="url(#arrow)"/>'
            )

    lines.append(
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto">'
        '<path d="M0,1 L9,5 L0,9 Z" fill="#555"/></marker></defs>'
    )

    for name, node in dag.nodes.items():
        if name not in positions:
            continue
        x, y = positions[name]
        style = _node_kind_style(node.kind)
        rect_attrs = " ".join(f'{k}="{v}"' for k, v in style.items())
        lines.append(
            f'<g class="node">'
            f'<rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" {rect_attrs}/>'
            f'<text x="{x + NODE_W // 2}" y="{y + NODE_H // 2}">{_label(node)[:18]}</text>'
            f"</g>"
        )

    lines.append("</svg>")
    svg = "\n".join(lines)
    if path:
        with open(path, "w") as f:
            f.write(svg)
    return svg


# ── Mermaid ────────────────────────────────────────────────────


def export_mermaid(dag: DAG) -> str:
    if not dag.nodes:
        return "flowchart TD\n"

    lines = ["flowchart TD"]
    node_ids: dict[str, str] = {}

    for i, name in enumerate(dag.nodes):
        nid = f"N{i}"
        node_ids[name] = nid
        node = dag.nodes[name]
        label = _label(node)
        safe_label = label.replace('"', "'").replace("\n", " ")
        if node.kind == "conditional":
            lines.append(f'    {nid}{{"{safe_label}"}}')
        elif node.kind == "loop":
            lines.append(f'    {nid}{{"{safe_label}"}}')
        elif node.kind == "parallel":
            lines.append(f'    {nid}["{safe_label}"]')
        elif node.kind == "subflow":
            lines.append(f'    {nid}["{safe_label}"]')
        else:
            lines.append(f'    {nid}["{safe_label}"]')

    for edge in dag.edges:
        src = node_ids.get(edge.source)
        tgt = node_ids.get(edge.target)
        if src is None or tgt is None:
            continue
        if edge.is_back_edge:
            lines.append(f"    {src} -.->|loop| {tgt}")
        else:
            lines.append(f"    {src} --> {tgt}")

    lines.append("")
    return "\n".join(lines)


# ── HTML ───────────────────────────────────────────────────────


def export_html(dag: DAG, path: str | None = None) -> str:
    svg = export_svg(dag)
    if not svg:
        return ""

    html = (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>Apex Flow</title>\n'
        '<style>\n'
        '  * { margin: 0; padding: 0; box-sizing: border-box; }\n'
        '  body { background: #0f0f1a; color: #eee; font-family: monospace; display: flex; flex-direction: column; align-items: center; padding: 20px; }\n'
        '  h1 { font-size: 16px; color: #e94560; margin-bottom: 16px; }\n'
        '  .container { background: #1a1a2e; border-radius: 12px; padding: 24px; max-width: 100%; overflow: auto; }\n'
        '  .container svg { display: block; }\n'
        '  .info { margin-top: 12px; font-size: 11px; color: #888; }\n'
        '  .info span { color: #e94560; }\n'
        '</style>\n'
        '</head>\n'
        '<body>\n'
        '<h1>Apex Flow</h1>\n'
        '<div class="container">\n'
        + svg + '\n'
        + '</div>\n'
        + '<div class="info"><span>legend:</span> &#9632; task &nbsp; <span style="color:#f5a623">&#9632;</span> conditional &nbsp; <span style="color:#4ecdc4">&#9632;</span> loop &nbsp; <span style="color:#a855f7">&#9632;</span> parallel</div>\n'
        '</body>\n'
        '</html>\n'
    )

    if path:
        with open(path, "w") as f:
            f.write(html)
    return html


# ── PNG ────────────────────────────────────────────────────────


def export_png(dag: DAG, path: str) -> None:
    try:
        import cairosvg
    except ImportError:
        raise ImportError(
            "PNG export requires cairosvg. Install with: pip install cairosvg"
        )
    svg = export_svg(dag)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=path)


# ── Unified API ────────────────────────────────────────────────

FORMATS = {"ascii", "svg", "mermaid", "html", "png"}


def render(dag: DAG, fmt: str = "ascii", path: str | None = None) -> str | None:
    fmt = fmt.lower()
    if fmt == "ascii":
        result = ascii_tree(dag)
        if path:
            with open(path, "w") as f:
                f.write(result)
        return result
    elif fmt == "svg":
        return export_svg(dag, path=path)
    elif fmt == "mermaid":
        result = export_mermaid(dag)
        if path:
            with open(path, "w") as f:
                f.write(result)
        return result
    elif fmt == "html":
        return export_html(dag, path=path)
    elif fmt == "png":
        export_png(dag, path)
        return None
    else:
        raise ValueError(f"Unknown format: {fmt!r}. Available: {', '.join(sorted(FORMATS))}")


# ── Tree Builder (ASCII) ───────────────────────────────────────


class _TreeBuilder:
    def __init__(self, dag: DAG):
        self.dag = dag
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
        display = _label(node)
        connector = "" if is_root else ("└── " if is_last else "├── ")
        self._lines.append(f"{prefix}{connector}{display}")
        children = self._children.get(name, [])
        child_prefix = prefix if is_root else (prefix + ("    " if is_last else "│   "))
        for i, child in enumerate(children):
            self._walk(child, child_prefix, i == len(children) - 1)
