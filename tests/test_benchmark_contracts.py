"""Development measurements must remain explicit, finite and scoped."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def suite_schema() -> dict[str, object]:
    """Return the development suite contract independently of its runner."""
    return json.loads(
        (ROOT / "tools/contracts/benchmark-suite.schema.json").read_text()
    )


@pytest.fixture
def suite() -> dict[str, object]:
    """Declare one explicit local executable and a finite measurement budget."""
    return {
        "version": "1.0.0",
        "id": "example",
        "cases": [
            {
                "id": "cold",
                "argv": ["python", "measure.py", "literal argument"],
                "cwd": ".",
                "repetitions": 3,
                "timeout_seconds": 10,
            }
        ],
    }


def test_benchmark_schemas_are_valid_draft7() -> None:
    for name in ["benchmark-suite", "benchmark-result"]:
        schema = json.loads((ROOT / f"tools/contracts/{name}.schema.json").read_text())
        jsonschema.Draft7Validator.check_schema(schema)


def test_explicit_argv_and_finite_budget_are_valid(
    suite_schema: dict[str, object], suite: dict[str, object]
) -> None:
    jsonschema.validate(suite, suite_schema)


@pytest.mark.parametrize(
    "field,value",
    [
        ("argv", "python measure.py; shell text"),
        ("argv", []),
        ("repetitions", 0),
        ("repetitions", 101),
        ("timeout_seconds", 0),
        ("timeout_seconds", 86401),
        ("shell", True),
    ],
)
def test_implicit_or_unbounded_execution_is_invalid(
    suite_schema: dict[str, object],
    suite: dict[str, object],
    field: str,
    value: object,
) -> None:
    document = copy.deepcopy(suite)
    document["cases"][0][field] = value
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, suite_schema)
