from __future__ import annotations

import threading
import time
import xml.etree.ElementTree as ET

import pytest

from apex.graph import (
    flow,
    task,
    state,
    parallel,
    CancelledError,
    RunResult,
)
from apex.graph._dag import DAG, Node
from apex.graph._viz import export_svg, export_mermaid, export_html


# ── BUG-5: escaping em _viz ──────────────────────────────────────


def test_svg_escapes_special_chars():
    dag = DAG()
    dag.add_node(Node(name="a", kind="task"))
    dag.add_node(Node(name="loop", kind="loop", condition="state.i < 3 & x"))
    dag.add_edge("a", "loop")
    dag.entry = "a"

    svg = export_svg(dag)
    ET.fromstring(svg)  # deve parsear como XML válido
    assert "&lt;" in svg
    assert "&amp;" in svg


def test_svg_unicode_and_emoji():
    dag = DAG()
    dag.add_node(Node(name="c", kind="conditional", condition="state.val == '😀'"))
    dag.entry = "c"

    svg = export_svg(dag)
    ET.fromstring(svg)


def test_svg_file_has_xml_declaration(tmp_path):
    dag = DAG()
    dag.add_node(Node(name="a", kind="task"))
    dag.entry = "a"

    path = tmp_path / "out.svg"
    export_svg(dag, path=str(path))
    content = path.read_text(encoding="utf-8")
    assert content.startswith('<?xml version="1.0" encoding="UTF-8"?>')


def test_mermaid_sanitizes_special_chars():
    dag = DAG()
    dag.add_node(Node(
        name="check",
        kind="conditional",
        condition="state.x > 0 & y in [1, 2] # foo; bar",
    ))
    dag.entry = "check"

    out = export_mermaid(dag)
    assert out.startswith("flowchart TD")
    assert "#" not in out
    assert ";" not in out
    assert "[" not in out
    assert "]" not in out
    # < > & permanecem como literais seguros dentro de aspas
    assert ">" in out
    assert "&" in out


def test_html_contains_escaped_svg():
    dag = DAG()
    dag.add_node(Node(name="loop", kind="loop", condition="state.i < 3"))
    dag.entry = "loop"

    html = export_html(dag)
    assert "<!DOCTYPE html>" in html
    assert "&lt;" in html  # SVG embutido com < escapado


def test_accented_function_name():
    def café():
        pass

    @flow
    def f():
        café()

    svg = f.viz("svg")
    ET.fromstring(svg)
    assert "café" in svg
    assert "café" in f.viz("mermaid")


# ── BUG-6: async def não pode ser silencioso ─────────────────────


def test_async_task_raises_typeerror():
    @task()
    async def atask():
        state.x = 1

    @flow
    def f():
        atask()

    with pytest.raises(TypeError, match="async def não suportado"):
        f.run()


def test_async_flow_raises_typeerror():
    @flow
    async def aflow():
        pass

    with pytest.raises(TypeError, match="async def não suportado"):
        aflow.run()


# ── RISCO-1: colisão de nome de retorno ──────────────────────────


def test_task_called_twice_uses_unique_keys():
    calls = []

    @task()
    def compute():
        calls.append(1)
        return len(calls)

    @flow
    def f():
        compute()
        compute()

    r = f.run()
    assert r.compute == 1
    assert r.compute_1 == 2


def test_return_collision_with_state_key_warns():
    @task()
    def compute():
        return 42

    @flow
    def f():
        compute()

    with pytest.warns(RuntimeWarning, match="pré-existente"):
        f.run(state={"compute": "original"})


# ── RISCO-2: condição inválida falha alto ────────────────────────


def test_condition_missing_key_raises():
    @flow
    def f():
        if state.undefined_key:
            pass

    with pytest.raises(RuntimeError, match="Falha ao avaliar condição"):
        f.run()


def test_condition_undefined_name_raises():
    @flow
    def f():
        if undefined_variable:  # noqa: F821
            pass

    with pytest.raises(RuntimeError, match="Falha ao avaliar condição"):
        f.run()


# ── API: cancel_event + run_detailed ─────────────────────────────


def test_cancel_event_before_start():
    started = []

    def a():
        started.append("a")

    def b():
        started.append("b")

    @flow
    def f():
        a()
        b()

    ev = threading.Event()
    ev.set()
    with pytest.raises(CancelledError):
        f.run(cancel_event=ev)
    assert started == []


def test_cancel_event_mid_flow():
    ran = []
    ev = threading.Event()

    def a():
        ran.append("a")
        ev.set()

    def b():
        ran.append("b")

    @flow
    def f():
        a()
        b()

    with pytest.raises(CancelledError):
        f.run(cancel_event=ev)
    assert ran == ["a"]


def test_cancel_event_in_loop():
    iterations = []
    ev = threading.Event()

    def bump():
        iterations.append(1)
        if len(iterations) >= 2:
            ev.set()

    @flow
    def f():
        while state.i < 100:
            bump()

    with pytest.raises(CancelledError):
        f.run(state={"i": 0}, cancel_event=ev)
    assert len(iterations) == 2


def test_run_detailed_results():
    @task()
    def compute():
        return 42

    @flow
    def f():
        compute()

    r = f.run_detailed()
    assert isinstance(r, RunResult)
    assert r.state.compute == 42
    assert r.results["compute"] == 42
    assert r.duration >= 0.0
    assert r.cancelled is False
    assert r.errors == []


def test_run_detailed_captures_error():
    @task()
    def boom():
        raise ValueError("boom")

    @flow
    def f():
        boom()

    r = f.run_detailed()
    assert len(r.errors) == 1
    assert isinstance(r.errors[0].__cause__, ValueError)


def test_run_detailed_captures_cancellation():
    ev = threading.Event()
    ev.set()

    @flow
    def f():
        pass

    r = f.run_detailed(cancel_event=ev)
    assert r.cancelled is True
    assert r.errors == []
