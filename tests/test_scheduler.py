from __future__ import annotations

import sys
sys.path.insert(0, ".")

import time
import threading
from apex.graph._scheduler import Flow, flow, task, parallel
from apex.graph._state import state


class TestFlowBasic:
    def test_empty_flow(self):
        @flow
        def empty():
            pass
        r = empty.run()
        assert r.to_dict() == {}

    def test_linear_execution(self):
        results = []

        def step1():
            results.append(1)
        def step2():
            results.append(2)

        @flow
        def linear():
            step1()
            step2()

        linear.run()
        assert results == [1, 2]

    def test_state_persistence(self):
        def set_val():
            state.x = 42

        @flow
        def writer():
            set_val()

        r = writer.run()
        assert r.x == 42

    def test_multiple_state_keys(self):
        def a():
            state.a = 1
        def b():
            state.b = 2

        @flow
        def multi():
            a()
            b()

        r = multi.run()
        assert r.a == 1 and r.b == 2

    def test_call_operator(self):
        def a():
            state.x = 1

        @flow
        def f():
            a()
        r = f()
        assert r.x == 1

    def test_name(self):
        @flow
        def my_name():
            pass
        assert repr(my_name) == "Flow('my_name')"


class TestFlowKwargs:
    def test_kwargs_as_state(self):
        @flow
        def adder():
            state.result = state.a + state.b
        r = adder.run(a=3, b=4)
        assert r.result == 7

    def test_kwargs_with_dict(self):
        @flow
        def merger():
            state.result = state.x + state.y
        r = merger.run(state={"x": 10}, y=20)
        assert r.result == 30

    def test_kwargs_override_dict(self):
        @flow
        def over():
            state.result = state.key
        r = over.run(state={"key": "original"}, key="override")
        assert r.result == "override"


class TestFlowConditional:
    def test_if_true(self):
        def set_val():
            state.flag = True
        def on_true():
            state.result = "yes"

        @flow
        def check():
            set_val()
            if state.flag:
                on_true()

        r = check.run()
        assert r.result == "yes"

    def test_if_false(self):
        def on_true():
            state.result = "yes"
        def on_false():
            state.result = "no"

        @flow
        def check():
            if False:
                on_true()
            else:
                on_false()

        r = check.run()
        assert r.result == "no"

    def test_if_else_branches(self):
        def if_branch():
            state.branch = "if"
        def else_branch():
            state.branch = "else"

        @flow
        def router():
            if state.cond:
                if_branch()
            else:
                else_branch()

        r1 = router.run(state={"cond": True})
        assert r1.branch == "if"
        r2 = router.run(state={"cond": False})
        assert r2.branch == "else"

    def test_if_no_else_with_task_after(self):
        def maybe():
            state.did_run = True
        def always():
            state.after = True

        @flow
        def test_flow():
            if state.flag:
                maybe()
            always()

        r = test_flow.run(state={"flag": False})
        assert "did_run" not in r.to_dict()
        assert r.after is True


class TestFlowLoop:
    def test_loop_basic(self):
        def increment():
            state.count += 1

        @flow
        def counter():
            while state.count < 3:
                increment()

        r = counter.run(state={"count": 0})
        assert r.count == 3

    def test_loop_with_condition_var(self):
        def step():
            state.i += 1
            if state.i >= 3:
                state.done = True

        @flow
        def looper():
            while not state.done:
                step()

        r = looper.run(state={"i": 0, "done": False})
        assert r.i == 3

    def test_loop_max_iterations(self):
        import pytest

        def never_stop():
            pass

        @flow
        def infinite():
            while True:
                never_stop()

        with pytest.raises(RuntimeError, match="excedeu limite"):
            infinite.run()

    def test_loop_body_side_effects(self):
        log = []

        def task_a():
            log.append("a")
        def task_b():
            log.append("b")
        def inc():
            state.count += 1

        @flow
        def looper():
            while state.count < 2:
                task_a()
                task_b()
                inc()

        looper.run(state={"count": 0})
        assert log == ["a", "b", "a", "b"]


class TestFlowParallel:
    def test_implicit_fork(self):
        results = []
        lock = threading.Lock()

        def task_a():
            with lock:
                results.append("a")
        def task_b():
            with lock:
                results.append("b")

        @flow
        def fork():
            task_a()
            task_b()

        fork.run()
        assert set(results) == {"a", "b"}

    def test_explicit_parallel(self):
        results = []
        lock = threading.Lock()

        def search():
            with lock:
                results.append("search")
        def docs():
            with lock:
                results.append("docs")

        @flow
        def explicit():
            with parallel():
                search()
                docs()

        explicit.run()
        assert set(results) == {"search", "docs"}


class TestFlowTaskConfig:
    def test_retry_recovery(self):
        attempt_counts = []

        @task(retry=3)
        def flaky():
            attempt_counts.append(1)
            if len(attempt_counts) < 3:
                raise RuntimeError("fail")

        def done():
            state.ok = True

        @flow
        def resilient():
            flaky()
            done()

        resilient.run()
        assert len(attempt_counts) == 3
        assert state.ok

    def test_timeout(self):
        import pytest

        @task(timeout=1)
        def slow():
            time.sleep(10)

        @flow
        def timed():
            slow()

        with pytest.raises(TimeoutError):
            timed.run()

    def test_task_return_value(self):
        @task()
        def compute():
            return 42

        def collect():
            state.answer = compute()

        @flow
        def ret_flow():
            collect()

        r = ret_flow.run()
        assert r.answer == 42


class TestFlowSubflow:
    def test_subflow_state_sharing(self):
        @flow
        def inner():
            state.inner_val = "from_inner"

        def after():
            state.seen = state.inner_val

        @flow
        def outer():
            inner()
            after()

        r = outer.run()
        assert r.inner_val == "from_inner"
        assert r.seen == "from_inner"

    def test_nested_subflow(self):
        l1_result = []
        l2_result = []
        l3_result = []

        def set_l1():
            state.l1 = True
            l1_result.append(1)

        def set_l2():
            state.l2 = state.l1
            l2_result.append(1)

        def set_l3():
            state.l3 = state.l2
            l3_result.append(1)

        @flow
        def level1():
            set_l1()

        @flow
        def level2():
            level1()
            set_l2()

        @flow
        def level3():
            level2()
            set_l3()

        r = level3.run()
        assert r.l1 and r.l2 and r.l3
        assert len(l1_result) == 1
        assert len(l2_result) == 1
        assert len(l3_result) == 1





class TestFlowEdgeCases:
    def test_viz_formats(self):
        def a():
            pass

        @flow
        def f():
            a()

        ascii_out = f.viz("ascii")
        assert isinstance(ascii_out, str) and len(ascii_out) > 0

        svg_out = f.viz("svg")
        assert "<svg" in svg_out

        mm_out = f.viz("mermaid")
        assert "flowchart" in mm_out

        html_out = f.viz("html")
        assert "<!DOCTYPE" in html_out

    def test_flow_repr(self):
        @flow(name="custom_name")
        def f():
            pass
        assert "custom_name" in repr(f)

    def test_map_returns_dag(self):
        def a():
            pass

        @flow
        def f():
            a()

        dag = f.map()
        assert "a" in dag.nodes
