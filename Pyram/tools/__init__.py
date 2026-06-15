from __future__ import annotations

import inspect
import json
from typing import Any, get_type_hints

from ..configs import Cache

# ── registro global ───────────────────────────────────────────
_registry: dict[str, dict] = {}
_cache = Cache("tools")


def tool(info: str = ""):
    """Registra uma função como ferramenta para tool calling."""
    def decorator(func):
        name = func.__name__
        hints = get_type_hints(func)
        sig = inspect.signature(func)
        doc = func.__doc__ or ""

        properties = {}
        required = []

        for pname, param in sig.parameters.items():
            if pname == "return":
                continue
            ptype = hints.get(pname, str)
            properties[pname] = {
                "type": _pytype_to_json(ptype),
                "description": info or doc or pname,
            }
            if param.default is inspect.Parameter.empty:
                required.append(pname)

        _registry[name] = {
            "name": name,
            "description": info or (doc.split("\n")[0] if doc else name),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            } if properties else {"type": "object", "properties": {}},
            "fn": func,
        }
        return func
    return decorator


def _pytype_to_json(tp: type) -> str:
    return {"str": "string", "int": "integer", "float": "number",
            "bool": "boolean", "list": "array", "dict": "object"}.get(tp.__name__, "string")


# ── schemas (nomes curtos) ────────────────────────────────────

def sch() -> list[dict]:
    """Schemas no formato OpenAI (DeepSeek/Groq/OpenAI)."""
    return [
        {"type": "function", "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        }}
        for t in _registry.values()
    ]


def sch_ant() -> list[dict]:
    """Schemas no formato Anthropic."""
    return [
        {"name": t["name"], "description": t["description"],
         "input_schema": t["parameters"]}
        for t in _registry.values()
    ]


def sch_gem() -> list[dict]:
    """Schemas no formato Gemini."""
    return [{"functionDeclarations": [
        {"name": t["name"], "description": t["description"],
         "parameters": t["parameters"]}
        for t in _registry.values()
    ]}]


# aliases legíveis
schemas = sch
schemas_anthropic = sch_ant
schemas_gemini = sch_gem
all = sch


def cache_clear():
    """Limpa o cache de resultados das tools."""
    _cache.clear()


# ── execução (nomes curtos) ───────────────────────────────────

def exec(response, use_cache: bool = False) -> list[dict]:
    """Executa tool_calls de um CompletionResponse."""
    return exec_tc(response.tool_calls, use_cache)


def exec_tc(tool_calls: list, use_cache: bool = False) -> list[dict]:
    """Executa uma lista de ToolCall objects.

    use_cache=True salva/recupera resultados em .PyramCache/tools/.
    """
    results = []
    for tc in tool_calls:
        entry = _registry.get(tc.name)
        if entry is None:
            results.append(erro(tc.id, tc.name, f"tool '{tc.name}' não registrada"))
            continue

        args = json.loads(tc.arguments) if tc.arguments else {}

        if use_cache:
            cached = _cache.get(args, key_prefix=tc.name)
            if cached is not None:
                results.append({"tool_call_id": tc.id, "name": tc.name, **cached})
                continue

        try:
            sig = inspect.signature(entry["fn"])
            bound = sig.bind(**args)
            output = entry["fn"](*bound.args, **bound.kwargs)
            content = json.dumps(output, ensure_ascii=False)

            if use_cache:
                _cache.set(args, {"content": content}, key_prefix=tc.name)

            results.append({"tool_call_id": tc.id, "name": tc.name, "content": content})
        except Exception as e:
            results.append(erro(tc.id, tc.name, str(e)))
    return results


# aliases legíveis
execute = exec
execute_tool_calls = exec_tc


# ── utilitários ───────────────────────────────────────────────

def clear():
    """Limpa o registro de ferramentas."""
    _registry.clear()


def erro(tool_call_id: str, name: str, msg: str) -> dict:
    return {"tool_call_id": tool_call_id, "name": name,
            "content": json.dumps({"erro": msg}, ensure_ascii=False)}


def listar() -> list[str]:
    """Lista nomes das ferramentas registradas."""
    return list(_registry.keys())
