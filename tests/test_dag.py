from __future__ import annotations

from apex.graph._dag import DAG, Node, Edge, NodeConfig, build_dag
from apex.graph._scheduler import Flow


class TestDAGCore:
    def test_empty_dag(self):
        d = DAG()
        assert d.nodes == {}
        assert d.edges == []

    def test_add_node(self):
        d = DAG()
        n = Node(name="a", kind="task")
        d.add_node(n)
        assert d.nodes["a"] == n

    def test_add_edge(self):
        d = DAG()
        d.add_node(Node(name="a", kind="task"))
        d.add_node(Node(name="b", kind="task"))
        d.add_edge("a", "b")
        assert len(d.edges) == 1
        assert d.edges[0].source == "a"
        assert d.edges[0].target == "b"


class TestDAGLevels:
    def test_linear(self):
        d = DAG()
        for n in ["a", "b", "c"]:
            d.add_node(Node(name=n, kind="task"))
        d.add_edge("a", "b")
        d.add_edge("b", "c")
        levels = d._levels()
        assert levels == [["a"], ["b"], ["c"]]

    def test_fork(self):
        d = DAG()
        for n in ["a", "b", "c", "d"]:
            d.add_node(Node(name=n, kind="task"))
        d.add_edge("a", "b")
        d.add_edge("a", "c")
        d.add_edge("b", "d")
        d.add_edge("c", "d")
        levels = d._levels()
        assert levels[0] == ["a"]
        assert set(levels[1]) == {"b", "c"}
        assert levels[2] == ["d"]

    def test_no_edges(self):
        d = DAG()
        d.add_node(Node(name="a", kind="task"))
        d.add_node(Node(name="b", kind="task"))
        levels = d._levels()
        assert set(levels[0]) == {"a", "b"}

    def test_back_edge_ignored_in_sort(self):
        d = DAG()
        for n in ["a", "b"]:
            d.add_node(Node(name=n, kind="task"))
        d.add_edge("a", "b")
        d.add_edge("b", "a", is_back_edge=True)
        levels = d._levels()
        assert levels == [["a"], ["b"]]


class TestDAGCycleDetection:
    def test_cycle_raises(self):
        d = DAG()
        for n in ["a", "b", "c"]:
            d.add_node(Node(name=n, kind="task"))
        d.add_edge("a", "b")
        d.add_edge("b", "c")
        d.add_edge("c", "a")
        import pytest
        with pytest.raises(ValueError, match="Cycle detected"):
            d._levels()

    def test_no_false_positive(self):
        d = DAG()
        for n in ["a", "b", "c"]:
            d.add_node(Node(name=n, kind="task"))
        d.add_edge("a", "b")
        d.add_edge("b", "c")
        d._levels()  # should not raise


class TestDAGBuild:
    def test_build_linear(self):
        def a():
            pass
        def b():
            pass
        def flow_fn():
            a()
            b()
        dag = build_dag(flow_fn)
        assert dag.entry == "a"
        assert len(dag.nodes) == 2
        assert len(dag.edges) == 1
        assert dag.edges[0].source == "a"
        assert dag.edges[0].target == "b"

    def test_build_if(self):
        def a():
            pass
        def b():
            pass
        def flow_fn():
            a()
            if True:
                b()
        dag = build_dag(flow_fn)
        assert dag.entry == "a"
        kinds = {n.name: n.kind for n in dag.nodes.values()}
        assert kinds["a"] == "task"
        assert kinds["if"] == "conditional"
        assert kinds["b"] == "task"

    def test_build_while(self):
        def a():
            pass
        def flow_fn():
            while False:
                a()
        dag = build_dag(flow_fn)
        kinds = {n.name: n.kind for n in dag.nodes.values()}
        assert kinds["loop"] == "loop"

    def test_build_with_parallel(self):
        def a():
            pass
        def b():
            pass
        def flow_fn():
            with parallel():
                a()
                b()
        dag = build_dag(flow_fn)
        kinds = {n.name: n.kind for n in dag.nodes.values()}
        assert any(k == "parallel" for k in kinds.values())

    def test_build_entry_if_first(self):
        def a():
            pass
        def flow_fn():
            if True:
                a()
        dag = build_dag(flow_fn)
        assert dag.entry == "if"

    def test_build_entry_while_first(self):
        def a():
            pass
        def flow_fn():
            while False:
                a()
        dag = build_dag(flow_fn)
        assert dag.entry == "loop"

    def test_resolve_closure(self):
        def outer():
            def inner():
                pass

            def flow_fn():
                inner()

            return build_dag(flow_fn)

        dag = outer()
        assert "inner" in dag.nodes

    def test_resolve_name_error(self):
        import pytest

        def flow_fn():
            undefined()  # noqa: F821

        with pytest.raises(NameError):
            build_dag(flow_fn)

    def test_node_config_via_task(self):
        from apex.graph._scheduler import task

        @task(retry=3, timeout=10)
        def my_task():
            pass

        def flow_fn():
            my_task()

        dag = build_dag(flow_fn)
        node = dag.nodes["my_task"]
        assert node.config.retry == 3
        assert node.config.timeout == 10
