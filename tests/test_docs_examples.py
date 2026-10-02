"""Executa os exemplos publicados na documentação.

Se um exemplo da doc parar de rodar, o CI quebra — a doc não pode prometer
comportamento que o código não entrega.

- `docs/examples.md`, `docs/agents-medium.md` e `docs/agents-complex.md`
  contêm programas completos: são executados de verdade.
- `docs/graph.md` e `docs/index.md` têm trechos ilustrativos: só precisam
  compilar.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parent.parent / "docs"

RUNNABLE = ["examples.md", "agents-medium.md", "agents-complex.md"]
COMPILE_ONLY = ["graph.md", "index.md"]

BLOCK_RE = re.compile(r"```python\n(.*?)```", re.S)


def _blocks(filename: str) -> list[str]:
    return BLOCK_RE.findall((DOCS / filename).read_text(encoding="utf-8"))


@pytest.mark.parametrize("filename", RUNNABLE)
def test_doc_examples_run(filename, tmp_path):
    blocks = _blocks(filename)
    assert blocks, f"nenhum bloco python encontrado em {filename}"

    import runpy
    import sys

    sys.path.insert(0, str(DOCS.parent))

    for index, block in enumerate(blocks):
        script = tmp_path / f"{filename.replace('.', '_')}_{index}.py"
        script.write_text(block, encoding="utf-8")
        try:
            runpy.run_path(str(script))
        except Exception as exc:  # noqa: BLE001 - queremos o erro no relatório
            pytest.fail(
                f"{filename} bloco #{index} falhou: "
                f"{type(exc).__name__}: {exc}"
            )


@pytest.mark.parametrize("filename", COMPILE_ONLY)
def test_doc_snippets_compile(filename):
    for index, block in enumerate(_blocks(filename)):
        try:
            compile(block, f"{filename}#{index}", "exec")
        except SyntaxError as exc:
            pytest.fail(f"{filename} bloco #{index} não compila: {exc}")
