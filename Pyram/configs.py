import os
from pathlib import Path

# Cache local no diretório de trabalho, igual __pycache__ / .pytest_cache
CACHE_DIR = Path(os.getcwd()) / ".PyramCache"


def get_cache_path(*parts: str) -> Path:
    """Retorna um subdiretório dentro de .PyramCache, criando se necessário."""
    path = CACHE_DIR.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path
