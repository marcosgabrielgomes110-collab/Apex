from __future__ import annotations

import threading
import xml.etree.ElementTree as ET

import pytest

from apex.graph import flow, state
from apex.graph._dag import DAG, Node
from apex.graph._state import _get_state
from apex.graph._viz import (
    ascii_tree,
    export_svg,
    export_mermaid,
    export_html,
    export_png,
    _layout_grid,
    _node_width,
    _truncate_label,
    NODE_W,
    MAX_LABEL_CHARS,
)


# ── RISCO-3: run reentrante + contextvar restaurado ──────────────


def test_concurrent_runs_isolated_state():
    def set_val():
        state.v = 1

    @flow
    def f():
        set_val()

    results = []

    def worker():
        results.append(f.run().v)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == [1] * 50


def test_contextvar_restored_after_success():
    def set_val():
        state.v = 1

    @flow
    def f():
        set_val()

    before = _get_state()
    r = f.run()
    after = _get_state()

    assert r.v == 1
    assert after is before  # sem vazar o estado do flow para fora


def test_contextvar_restored_after_exception():
    def boom():
        state.x = "leaked"
        raise ValueError("boom")

    @flow
    def f():
        boom()

    before = _get_state()
    with pytest.raises(RuntimeError):
        f.run()
    after = _get_state()

    assert after is before  # nada de vazar o estado parcial


def test_ensure_dag_is_cached():
    def a():
        pass

    @flow
    def f():
        a()

    dag1 = f._ensure_dag()
    dag2 = f._ensure_dag()
    assert dag1 is dag2


# ── MELHORIA-3: viz vazio coerente + layout largo ────────────────


def test_empty_graph_all_formats(tmp_path):
    dag = DAG()

    assert ascii_tree(dag) == "(empty graph)"

    svg = export_svg(dag)
    ET.fromstring(svg)
    assert "(empty graph)" in svg

    mm = export_mermaid(dag)
    assert "(empty graph)" in mm

    html = export_html(dag)
    assert "<!DOCTYPE html>" in html
    assert "(empty graph)" in html

    # PNG requer cairosvg (dependência opcional); sem ele, ImportError.
    with pytest.raises(ImportError, match="cairosvg"):
        export_png(dag, str(tmp_path / "empty.png"))


def test_wide_graph_does_not_overflow():
    dag = DAG()
    n = 50
    for i in range(n):
        dag.add_node(Node(name=f"n{i}", kind="task"))
    for i in range(n - 1):
        dag.add_edge(f"n{i}", f"n{i + 1}")
    dag.entry = "n0"

    levels, positions, w, h = _layout_grid(dag)
    assert len(levels) == n
    assert w > n * NODE_W  # largura suficiente para os 50 níveis
    for x, y in positions.values():
        assert 0 <= x < w
        assert 0 <= y < h


def test_node_width_grows_with_long_label():
    dag = DAG()
    dag.add_node(Node(name="a", kind="task"))
    dag.add_node(Node(name="b", kind="conditional", condition="x" * 60))
    dag.add_edge("a", "b")
    dag.entry = "a"

    assert _node_width(dag) > NODE_W


def test_label_truncated_with_ellipsis():
    long = "x" * 100
    truncated = _truncate_label(long)
    assert len(truncated) <= MAX_LABEL_CHARS
    assert truncated.endswith("…")
