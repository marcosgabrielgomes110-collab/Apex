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
            d[name] = {}
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

    def __getattr__(self, name: str) -> Any:
        try:
            st = _current.get()
        except LookupError:
            st = State()
            _current.set(st)
        return getattr(st, name)

    def __setattr__(self, name: str, value) -> None:
        try:
            st = _current.get()
        except LookupError:
            st = State()
            _current.set(st)
        setattr(st, name, value)

    def __delattr__(self, name: str) -> None:
        try:
            st = _current.get()
        except LookupError:
            st = State()
            _current.set(st)
        delattr(st, name)

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
