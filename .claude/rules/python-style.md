---
paths:
  - git-miner/**/*.py
  - predictor/**/*.py
  - report-engine/**/*.py
---

# Python Style Rules

## Version and Formatter
- Python 3.11+
- Formatter: `black` (line length 88) — auto-applied by auto-lint.sh hook
- Linter: `ruff` — auto-applied by auto-lint.sh hook

## Type Hints
- ALL functions must have type hints on parameters and return value
- Use `from __future__ import annotations` for forward references
- Use `list[X]`, `dict[K, V]`, `tuple[X, Y]` (lowercase, Python 3.11+ style)

## Documentation
- Docstrings on every public function and class (Google style)
- Format: `Args:`, `Returns:`, `Raises:` sections where applicable

## Code Style
- No bare `except:` — always catch specific exceptions
- No mutable default arguments (`def f(x=[])` is forbidden)
- Use `pathlib.Path` for all file paths — not `os.path`
- Use `dataclasses` or `pydantic` for data structures — not plain dicts

## Imports
- Group: stdlib → third-party → local (with blank line between groups)
- No wildcard imports (`from x import *`)

## Testing
- All new functions must have corresponding pytest tests in `tests/`
- Use `pytest.fixture` for shared setup — no setup/teardown methods
