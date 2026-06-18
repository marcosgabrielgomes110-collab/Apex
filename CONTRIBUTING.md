# Contributing to Apex

Thanks for your interest in contributing! Apex is a zero-dependency Python workflow engine.

## Getting Started

```bash
git clone https://github.com/marcosgabrielgomes110-collab/Apex.git
cd apex
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Project Structure

```
apex/
├── __init__.py          # Package entry
├── __version__.py       # Version info
└── graph/               # Workflow engine
    ├── __init__.py      # Flow, flow, task, state, parallel
    ├── _state.py        # State + _StateProxy + contextvars
    ├── _dag.py          # AST walker → DAG + cycle detection
    ├── _scheduler.py    # Flow, @flow, @task, executor, retry, timeout
    └── _viz.py          # ASCII, SVG, Mermaid, HTML, PNG
```

## Code Style

- Pure Python functions — no classes unless necessary
- Type hints on all public APIs
- `from __future__ import annotations` in every file
- Single quotes for strings
- Docstrings in Portuguese (consistent with existing codebase)

## Pull Request Checklist

- [ ] All tests pass: `python -m pytest tests/ -v`
- [ ] New features include tests
- [ ] Documentation updated if API changes
- [ ] Type hints present on new public functions
- [ ] No new dependencies added

## Questions?

Open an issue or reach out directly.
