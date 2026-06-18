from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_current: ContextVar = ContextVar("graph_state")


class State:
    """Container mutável com criação automática de atributos aninhados."""

    def __init__(self, data: dict | None = None):
        object.__setattr__(self, "_data", data or {})

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        d = object.__getattribute__(self, "_data")
        if name not in d:
            raise AttributeError(
                f"State key '{name}' not found. Initialize it first, e.g.: "
                f"flow.run(state={{{name!r}: ...}})"
            )
        val = d[name]
        if isinstance(val, dict):
            return State(val)
        return val

    def __setattr__(self, name: str, value) -> None:
        d = object.__getattribute__(self, "_data")
        d[name] = value

    def __delattr__(self, name: str) -> None:
        d = object.__getattribute__(self, "_data")
        if name in d:
            del d[name]

    def __getitem__(self, key: str) -> Any:
        return self.__getattr__(key)

    def __setitem__(self, key: str, value) -> None:
        self.__setattr__(key, value)

    def __bool__(self) -> bool:
        d = object.__getattribute__(self, "_data")
        return bool(d)

    def __len__(self) -> int:
        d = object.__getattribute__(self, "_data")
        return len(d)

    def to_dict(self) -> dict:
        d = object.__getattribute__(self, "_data")
        result = {}
        for k, v in d.items():
            if isinstance(v, State):
                result[k] = v.to_dict()
            else:
                result[k] = v
        return result

    @classmethod
    def from_dict(cls, data: dict) -> State:
        st = cls(data)
        return st

    def copy(self) -> State:
        import copy
        return State(copy.deepcopy(object.__getattribute__(self, "_data")))

    def __repr__(self) -> str:
        d = object.__getattribute__(self, "_data")
        return f"State({d!r})"

    def __contains__(self, key: str) -> bool:
        d = object.__getattribute__(self, "_data")
        return key in d

    def __eq__(self, other) -> bool:
        if isinstance(other, State):
            return object.__getattribute__(self, "_data") == object.__getattribute__(other, "_data")
        return False


class _StateProxy:
    """Proxy module-level que delega ao State ativo no ContextVar."""

    def _get(self) -> State:
        try:
            return _current.get()
        except LookupError:
            st = State()
            _current.set(st)
            return st

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get(), name)

    def __setattr__(self, name: str, value) -> None:
        setattr(self._get(), name, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._get(), name)

    def __contains__(self, key: str) -> bool:
        try:
            st = _current.get()
        except LookupError:
            return False
        return key in st

    def __repr__(self) -> str:
        try:
            st = _current.get()
        except LookupError:
            return "State({})"
        return repr(st)

    def __eq__(self, other) -> bool:
        try:
            st = _current.get()
        except LookupError:
            return False
        return st == other


def _set_state(st: State) -> None:
    _current.set(st)


def _get_state() -> State:
    try:
        return _current.get()
    except LookupError:
        st = State()
        _current.set(st)
        return st


# singleton público
state = _StateProxy()
