from __future__ import annotations

import threading
from apex.graph._state import State, _StateProxy, _set_state, _get_state


class TestStateCore:
    def test_init_empty(self):
        s = State()
        assert len(s) == 0
        assert bool(s) is False

    def test_init_with_data(self):
        s = State({"a": 1, "b": "x"})
        assert s.a == 1
        assert s.b == "x"

    def test_set_and_get(self):
        s = State()
        s.x = 42
        assert s.x == 42

    def test_get_missing_raises(self):
        s = State()
        import pytest
        with pytest.raises(AttributeError, match="not found"):
            _ = s.nao_existe

    def test_get_private_raises(self):
        s = State()
        import pytest
        with pytest.raises(AttributeError):
            _ = s._internal

    def test_update_existing(self):
        s = State({"count": 0})
        s.count += 1
        assert s.count == 1

    def test_delete(self):
        s = State({"x": 1})
        del s.x
        assert "x" not in s

    def test_contains(self):
        s = State({"a": 1})
        assert "a" in s
        assert "b" not in s


class TestStateToFromDict:
    def test_to_dict(self):
        s = State({"a": 1, "b": {"c": 2}})
        d = s.to_dict()
        assert d == {"a": 1, "b": {"c": 2}}

    def test_from_dict(self):
        s = State.from_dict({"x": 10})
        assert s.x == 10

    def test_roundtrip(self):
        original = {"name": "test", "value": 42}
        s = State(original)
        assert s.to_dict() == original


class TestStateCopy:
    def test_copy_is_independent(self):
        s = State({"x": 1})
        c = s.copy()
        c.x = 2
        assert s.x == 1

    def test_copy_deep(self):
        s = State({"nested": {"a": 1}})
        c = s.copy()
        c.nested["a"] = 99
        assert s.nested["a"] == 1


class TestStateProxy:
    def test_proxy_get_set(self):
        sp = _StateProxy()
        sp.val = "hello"
        assert sp.val == "hello"

    def test_proxy_contains(self):
        sp = _StateProxy()
        sp.key = True
        assert "key" in sp

    def test_proxy_missing_raises(self):
        sp = _StateProxy()
        import pytest
        with pytest.raises(AttributeError):
            _ = sp.non_existent


class TestStateContextVars:
    def test_isolation(self):
        results = []

        def worker(val):
            _set_state(State({"val": val}))
            st = _get_state()
            results.append(st.val)

        t1 = threading.Thread(target=worker, args=(10,))
        t2 = threading.Thread(target=worker, args=(20,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert sorted(results) == [10, 20]

    def test_proxy_thread_isolation(self):
        results = []
        sp = _StateProxy()

        def worker(val):
            sp.val = val
            import time
            time.sleep(0.01)
            results.append(sp.val)

        t1 = threading.Thread(target=worker, args=("a",))
        t2 = threading.Thread(target=worker, args=("b",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert set(results) == {"a", "b"}


class TestStateEdgeCases:
    def test_nested_dict_access(self):
        s = State({"config": {"host": "localhost", "port": 8080}})
        assert s.config.host == "localhost"
        assert s.config.port == 8080

    def test_nested_modify(self):
        s = State({"nested": {"x": 1}})
        s.nested.x = 99
        assert s.nested.x == 99

    def test_bool_empty(self):
        assert bool(State()) is False

    def test_bool_nonempty(self):
        assert bool(State({"a": 1})) is True

    def test_repr(self):
        s = State({"a": 1})
        r = repr(s)
        assert "State" in r
        assert "a" in r

    def test_eq(self):
        s1 = State({"x": 1})
        s2 = State({"x": 1})
        s3 = State({"x": 2})
        assert s1 == s2
        assert s1 != s3
        assert s1 != {"x": 1}
