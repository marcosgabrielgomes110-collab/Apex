from __future__ import annotations

import sys
sys.path.insert(0, ".")

from apex.graph import flow, task, state


class TestIntegration:
    def test_full_workflow(self):
        @task(retry=1)
        def validate():
            state.valid = state.input is not None

        @task()
        def process():
            state.result = state.input * 2

        @flow(name="full_flow")
        def pipeline():
            validate()
            if state.valid:
                process()

        r = pipeline.run(input=21)
        assert r.valid is True
        assert r.result == 42

    def test_loop_with_conditional_exit(self):
        def step():
            state.i += 1
            if state.i >= 5:
                state.done = True

        @flow
        def agent():
            while not state.done:
                step()

        r = agent.run(state={"i": 0, "done": False})
        assert r.i == 5
        assert r.done is True

    def test_nested_conditionals(self):
        def set_a():
            state.a = True
        def set_b():
            state.b = True
        def set_c():
            state.c = True

        @flow
        def nested():
            set_a()
            if state.a:
                set_b()
                if state.b:
                    set_c()

        r = nested.run()
        assert r.a and r.b and r.c

    def test_parallel_with_results(self):
        results = set()

        def task_a():
            results.add("a")
        def task_b():
            results.add("b")
        def task_c():
            results.add("c")

        @flow
        def parallel_flow():
            task_a()
            task_b()
            task_c()

        parallel_flow.run()
        assert results == {"a", "b", "c"}

    def test_mixed_loop_and_conditional(self):
        def think():
            state.thoughts += 1

        def decide():
            if state.thoughts >= 3:
                state.found = True

        @flow
        def search():
            while not state.found:
                think()
                decide()

        r = search.run(state={"thoughts": 0, "found": False})
        assert r.thoughts == 3
        assert r.found is True

    def test_state_clean_between_runs(self):
        first_val = []
        second_val = []

        def set_val():
            first_val.append(1)
            state.val = "first"

        def set_other():
            second_val.append(1)
            state.other = "second"

        @flow
        def f1():
            set_val()

        @flow
        def f2():
            set_other()

        r1 = f1.run()
        assert r1.val == "first"

        r2 = f2.run()
        assert "val" not in r2.to_dict()
        assert r2.other == "second"

    def test_viz_all_formats(self):
        def a():
            pass

        @flow
        def f():
            a()

        f.viz("ascii")
        f.viz("svg")
        f.viz("mermaid")
        f.viz("html")
