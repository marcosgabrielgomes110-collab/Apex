from __future__ import annotations

from apex.graph._dag import DAG, Node
from apex.graph._viz import (
    ascii_tree, export_svg, export_mermaid, export_html,
    export_png, render, _layout_grid,
)


def _make_test_dag() -> DAG:
    dag = DAG()
    dag.add_node(Node(name="start", kind="task"))
    dag.add_node(Node(name="check", kind="conditional", condition="state.x > 0"))
    dag.add_node(Node(name="process", kind="task"))
    dag.add_node(Node(name="loop_node", kind="loop", condition="state.retry"))
    dag.add_node(Node(name="end", kind="task"))
    dag.add_edge("start", "check")
    dag.add_edge("check", "process")
    dag.add_edge("process", "loop_node")
    dag.add_edge("loop_node", "end")
    dag.entry = "start"
    return dag


class TestASCII:
    def test_empty(self):
        assert ascii_tree(DAG()) == "(empty)"

    def test_single_node(self):
        dag = DAG()
        dag.add_node(Node(name="a", kind="task"))
        dag.entry = "a"
        assert "a" in ascii_tree(dag)

    def test_multi_node(self):
        dag = _make_test_dag()
        out = ascii_tree(dag)
        assert "start" in out
        assert "? state.x > 0" in out
        assert "process" in out
        assert "\u21bb state.retry" in out
        assert "end" in out

    def test_conditional_prefix(self):
        dag = DAG()
        dag.add_node(Node(name="if", kind="conditional", condition="x == 1"))
        dag.entry = "if"
        out = ascii_tree(dag)
        assert "?" in out

    def test_loop_prefix(self):
        dag = DAG()
        dag.add_node(Node(name="loop", kind="loop", condition="x < 3"))
        dag.entry = "loop"
        out = ascii_tree(dag)
        assert "\u21bb" in out

    def test_parallel_label(self):
        dag = DAG()
        dag.add_node(Node(name="p", kind="parallel"))
        dag.entry = "p"
        out = ascii_tree(dag)
        assert "parallel" in out


class TestSVG:
    def test_empty(self):
        assert export_svg(DAG()) == ""

    def test_valid_xml(self):
        import xml.etree.ElementTree as ET
        dag = _make_test_dag()
        svg = export_svg(dag)
        root = ET.fromstring(svg)
        assert root.tag.endswith("svg")

    def test_has_nodes(self):
        import xml.etree.ElementTree as ET
        dag = _make_test_dag()
        svg = export_svg(dag)
        root = ET.fromstring(svg)
        rects = root.findall(".//{http://www.w3.org/2000/svg}rect")
        assert len(rects) == 5

    def test_file_output(self, tmp_path):
        dag = _make_test_dag()
        path = tmp_path / "test.svg"
        export_svg(dag, path=str(path))
        assert path.exists()
        assert "<svg" in path.read_text()

    def test_back_edge_styling(self):
        dag = DAG()
        dag.add_node(Node(name="a", kind="task"))
        dag.add_node(Node(name="b", kind="task"))
        dag.add_edge("a", "b")
        dag.add_edge("b", "a", is_back_edge=True)
        dag.entry = "a"
        svg = export_svg(dag)
        assert "edge-back" in svg


class TestMermaid:
    def test_empty(self):
        out = export_mermaid(DAG())
        assert "flowchart" in out

    def test_valid_syntax(self):
        dag = _make_test_dag()
        out = export_mermaid(dag)
        assert out.startswith("flowchart TD")
        assert "-->" in out

    def test_has_all_nodes(self):
        dag = _make_test_dag()
        out = export_mermaid(dag)
        assert "start" in out
        assert "process" in out
        assert "end" in out

    def test_conditional_style(self):
        dag = DAG()
        dag.add_node(Node(name="if", kind="conditional", condition="x"))
        dag.entry = "if"
        out = export_mermaid(dag)
        assert "{" in out

    def test_loop_style(self):
        dag = DAG()
        dag.add_node(Node(name="loop", kind="loop", condition="x"))
        dag.entry = "loop"
        out = export_mermaid(dag)
        assert "{" in out


class TestHTML:
    def test_empty(self):
        assert export_html(DAG()) == ""

    def test_valid_html(self):
        dag = _make_test_dag()
        html = export_html(dag)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_contains_svg(self):
        dag = _make_test_dag()
        html = export_html(dag)
        assert "<svg" in html

    def test_file_output(self, tmp_path):
        dag = _make_test_dag()
        path = tmp_path / "test.html"
        export_html(dag, path=str(path))
        assert path.exists()
        assert "<svg" in path.read_text()


class TestPNG:
    def test_missing_cairosvg(self):
        import pytest
        dag = _make_test_dag()
        with pytest.raises(ImportError, match="cairosvg"):
            export_png(dag, "/tmp/_test.png")


class TestRender:
    def test_unknown_format(self):
        import pytest
        dag = _make_test_dag()
        with pytest.raises(ValueError, match="Unknown format"):
            render(dag, fmt="pdf")

    def test_ascii(self):
        dag = _make_test_dag()
        out = render(dag, fmt="ascii")
        assert isinstance(out, str)

    def test_svg(self):
        dag = _make_test_dag()
        out = render(dag, fmt="svg")
        assert "<svg" in out

    def test_mermaid(self):
        dag = _make_test_dag()
        out = render(dag, fmt="mermaid")
        assert "flowchart" in out

    def test_html(self):
        dag = _make_test_dag()
        out = render(dag, fmt="html")
        assert "<!DOCTYPE" in out

    def test_ascii_to_file(self, tmp_path):
        dag = _make_test_dag()
        path = tmp_path / "out.txt"
        render(dag, fmt="ascii", path=str(path))
        assert path.exists()


class TestLayout:
    def test_empty_dag(self):
        dag = DAG()
        levels, positions, w, h = _layout_grid(dag)
        assert positions == {}

    def test_single_node(self):
        dag = DAG()
        dag.add_node(Node(name="a", kind="task"))
        dag.entry = "a"
        levels, positions, w, h = _layout_grid(dag)
        assert "a" in positions
        assert w > 0
        assert h > 0

    def test_two_levels(self):
        dag = DAG()
        dag.add_node(Node(name="a", kind="task"))
        dag.add_node(Node(name="b", kind="task"))
        dag.add_edge("a", "b")
        dag.entry = "a"
        levels, positions, w, h = _layout_grid(dag)
        pos_a = positions["a"]
        pos_b = positions["b"]
        assert pos_b[0] > pos_a[0]  # b is to the right
