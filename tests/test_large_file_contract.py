"""Keep native byte limits and visible skip reasons within shared contracts."""

import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_large_header_budget_is_an_explicit_positive_byte_setting() -> None:
    schema = json.loads(
        (ROOT / "python/cppulse/data/project_config.schema.json").read_text()
    )
    jsonschema.Draft7Validator.check_schema(schema)
    jsonschema.validate({"max_file_bytes": 64 * 1024 * 1024}, schema)
    for value in [0, -1, 1.5, True, "16777216", 2**63]:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"max_file_bytes": value}, schema)


@pytest.mark.parametrize(
    "path",
    [
        "docs/schemas/findings.schema.json",
        "python/cppulse/contracts/schemas/prototype_v1/findings.schema.json",
    ],
)
def test_skipped_file_reason_is_preserved_without_fabricating_parse_context(
    path: str,
) -> None:
    schema = json.loads((ROOT / path).read_text())
    document = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/declared",
            "analyzed_at": "2026-11-14T00:00:00Z",
            "file_count": 1,
            "total_loc": 0,
            "analysis": {
                "enabled_rules": ["CPP-CX-001"],
                "files": [
                    {
                        "path": "include/distributed.hpp",
                        "status": "skipped",
                        "compile_context": "none",
                        "error_count": 0,
                        "reason": "File exceeds configured max_file_bytes=16777216",
                    }
                ],
            },
        },
        "findings": [],
        "summary": {"total_findings": 0, "by_category": {}, "by_severity": {}},
    }
    jsonschema.validate(document, schema)
    document["metadata"]["analysis"]["files"][0]["reason"] = ""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, schema)
