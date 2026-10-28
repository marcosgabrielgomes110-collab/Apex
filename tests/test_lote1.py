from __future__ import annotations

import time

import pytest

from apex.graph import flow, task, state, parallel


# ── BUG-1: subflow compartilha o State do pai ─────────────────────


def test_subflow_preserves_parent_state():
    @flow
    def inner():
        state.inner_val = "from_inner"

    def before():
        state.before_val = "B"

    def after():
        state.seen_before = state.get("before_val", "MISSING")

    @flow
    def outer():
        before()
        inner()
        after()

    r = outer.run()
    assert r.before_val == "B"
    assert r.seen_before == "B"
    assert r.inner_val == "from_inner"


def test_subflow_node_kind_is_subflow():
    @flow
    def inner():
        state.inner_val = "x"

    @flow
    def outer():
        inner()

    dag = outer.map()
    kinds = {n.name: n.kind for n in dag.nodes.values()}
    assert kinds["inner"] == "subflow"


def test_subflow_with_task_body_shares_state():
    def do_work():
        state.work_done = True

    @flow
    def inner():
        do_work()

    def before():
        state.prior = "kept"

    @flow
    def outer():
        before()
        inner()

    r = outer.run()
    assert r.prior == "kept"
    assert r.work_done is True


# ── BUG-2: controle de fluxo aninhado ─────────────────────────────


def test_nested_conditional_false_does_not_run():
    def set_c():
        state.c = True

    @flow
    def nested():
        if True:
            if False:
                set_c()

    r = nested.run()
    assert "c" not in r.to_dict()


def test_nested_conditional_true_runs():
    def set_c():
        state.c = True

    @flow
    def nested():
        if True:
            if True:
                set_c()

    r = nested.run()
    assert r.c is True


def test_conditional_in_loop_respects_false_branch():
    def mark_wrong():
        state.wrong = True

    def bump():
        state.i += 1

    @flow
    def loopy():
        while state.i < 2:
            if state.i > 100:
                mark_wrong()
            bump()

    r = loopy.run(state={"i": 0})
    assert r.i == 2
    assert "wrong" not in r.to_dict()


def test_conditional_in_loop_reevaluates_true():
    def mark():
        state.marked = True

    def bump():
        state.i += 1

    @flow
    def loopy():
        while state.i < 3:
            if state.i == 2:
                mark()
            bump()

    r = loopy.run(state={"i": 0})
    assert r.i == 3
    assert r.marked is True


# ── BUG-3: timeout retorna no limite, exceção preservada ──────────


def test_timeout_returns_promptly():
    @task(timeout=1)
    def slow():
        time.sleep(4)
        state.slow_finished = True

    @flow
    def timed():
        slow()

    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        timed.run()
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0


def test_task_exception_preserves_cause():
    @task()
    def boom():
        raise ValueError("boom")

    @flow
    def f():
        boom()

    with pytest.raises(RuntimeError) as exc_info:
        f.run()
    assert isinstance(exc_info.value.__cause__, ValueError)


# ── BUG-4: merge paralelo determinístico + conflito ───────────────


def test_parallel_distinct_keys_merge():
    def task_a():
        state.a = 1

    def task_b():
        state.b = 2

    @flow
    def par():
        with parallel():
            task_a()
            task_b()

    r = par.run()
    assert r.a == 1 and r.b == 2


def test_parallel_conflicting_write_raises():
    def task_a():
        state.counter = 1

    def task_b():
        state.counter = 2

    @flow
    def par():
        with parallel():
            task_a()
            task_b()

    with pytest.raises(RuntimeError, match="Conflito"):
        par.run()


def test_parallel_accumulator_conflict_raises():
    def add_a():
        state.total += 10

    def add_b():
        state.total += 20

    @flow
    def acc():
        with parallel():
            add_a()
            add_b()

    with pytest.raises(RuntimeError, match="Conflito"):
        acc.run(state={"total": 0})


def test_parallel_distinct_keys_stress():
    def task_a():
        state.a = 1

    def task_b():
        state.b = 2
        state.c = 3

    @flow
    def par():
        with parallel():
            task_a()
            task_b()

    for _ in range(50):
        r = par.run()
        assert r.a == 1
        assert r.b == 2
        assert r.c == 3
