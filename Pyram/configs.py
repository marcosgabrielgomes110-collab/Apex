from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

# Cache local — pode ser configurado via PYRAM_CACHE_DIR env var
# Padrão: .PyramCache no diretório de trabalho (como __pycache__ / .pytest_cache)
_CACHE_DIR_ENV = os.environ.get("PYRAM_CACHE_DIR")
CACHE_DIR = Path(_CACHE_DIR_ENV) if _CACHE_DIR_ENV else Path(os.getcwd()) / ".PyramCache"


def get_cache_path(*parts: str) -> Path:
    """Retorna um subdiretório dentro de .PyramCache, criando se necessário."""
    path = CACHE_DIR.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


class Cache:
    """Cache unificado baseado em hash, usado por LLM, tools e graph.

    Uso:
        cache = Cache("deepseek", ttl=3600)
        if hit := cache.get(payload):
            return hit
        ...
        cache.set(payload, response)

        # cache de tools
        tc = Cache("tools")
        if hit := tc.get(args, key_prefix="minha_tool"):
            return hit
        tc.set(args, result, key_prefix="minha_tool")
    """

    def __init__(self, namespace: str, ttl: int = 0):
        self._dir = get_cache_path(namespace)
        self._ttl = ttl

    def _hash(self, raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def _key(self, payload: dict | str, key_prefix: str = "") -> str:
        if isinstance(payload, dict):
            raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        else:
            raw = payload
        prefix = f"{key_prefix}:" if key_prefix else ""
        return prefix + self._hash(raw)

    def _path(self, key: str) -> Path:
        return self._dir / key

    def get(self, payload: dict | str, *, key_prefix: str = "") -> dict | None:
        """Retorna dados cacheados ou None se expirado/inexistente."""
        path = self._path(self._key(payload, key_prefix))
        if not path.exists():
            return None
        if self._ttl > 0:
            age = time.time() - path.stat().st_mtime
            if age > self._ttl:
                path.unlink(missing_ok=True)
                return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            path.unlink(missing_ok=True)
            return None

    def set(self, payload: dict | str, data: Any, *, key_prefix: str = "") -> None:
        """Salva dados no cache."""
        path = self._path(self._key(payload, key_prefix))
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def exists(self, payload: dict | str, *, key_prefix: str = "") -> bool:
        """Verifica se entrada existe e não expirou (sem ler o conteúdo)."""
        path = self._path(self._key(payload, key_prefix))
        if not path.exists():
            return False
        if self._ttl > 0:
            if time.time() - path.stat().st_mtime > self._ttl:
                path.unlink(missing_ok=True)
                return False
        return True

    def clear(self) -> None:
        """Remove todos os arquivos do namespace."""
        for p in self._dir.iterdir():
            if p.is_file():
                p.unlink()

    def remove(self, payload: dict | str, *, key_prefix: str = "") -> None:
        """Remove uma entrada específica."""
        self._path(self._key(payload, key_prefix)).unlink(missing_ok=True)
