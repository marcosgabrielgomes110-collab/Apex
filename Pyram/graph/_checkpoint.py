from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..configs import get_cache_path


class CheckpointManager:
    """Gerencia checkpoint e cache de tasks para um flow."""

    def __init__(self, flow_name: str):
        self.flow_name = flow_name
        self._base = get_cache_path("graph", flow_name)
        self._checkpoint_dir = self._base / "checkpoints"
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)

        from ..configs import Cache
        self._cache = Cache(f"graph/{flow_name}/cache")

    # ── checkpoint ──────────────────────────────────────────

    def save(self, node_name: str, state_dict: dict) -> None:
        path = self._checkpoint_dir / f"{node_name}.json"
        payload = {
            "node": node_name,
            "state": state_dict,
            "timestamp": time.time(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    def load(self, node_name: str) -> dict | None:
        path = self._checkpoint_dir / f"{node_name}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
            return payload.get("state")
        except (json.JSONDecodeError, KeyError):
            path.unlink(missing_ok=True)
            return None

    def save_manifest(self, completed: list[str]) -> None:
        path = self._base / "manifest.json"
        path.write_text(json.dumps(completed, ensure_ascii=False))

    def load_manifest(self) -> list[str]:
        path = self._base / "manifest.json"
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, TypeError):
            return []

    def clear_all(self) -> None:
        for p in self._checkpoint_dir.iterdir():
            if p.is_file():
                p.unlink()
        m = self._base / "manifest.json"
        m.unlink(missing_ok=True)
        self._cache.clear()

    # ── cache ───────────────────────────────────────────────

    def cache_get(self, node_name: str, args: dict) -> Any | None:
        return self._cache.get(args, key_prefix=node_name)

    def cache_set(self, node_name: str, args: dict, result: Any) -> None:
        self._cache.set(args, result, key_prefix=node_name)

    def cache_clear(self) -> None:
        self._cache.clear()
