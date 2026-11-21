"""Validate the assurance contracts before implementing their producers."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMAS = Path(__file__).resolve().parents[1] / "docs" / "schemas"


@pytest.mark.parametrize(
    "path", sorted(SCHEMAS.glob("*.schema.json")), ids=lambda p: p.name
)
def test_contract_is_draft_seven(path: Path) -> None:
    """Every pipeline contract remains a valid draft-07 schema."""
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    jsonschema.Draft7Validator.check_schema(schema)


def test_legacy_findings_remain_compatible() -> None:
    """Coverage metadata is additive for existing reports and consumers."""
    schema = json.loads((SCHEMAS / "findings.schema.json").read_text())
    data = json.loads(
        (SCHEMAS.parents[1] / "examples" / "fmt" / "findings.json").read_text()
    )
    jsonschema.validate(data, schema)
