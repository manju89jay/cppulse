"""Validate the existing project configuration shape before CLI consumption."""

import json
from pathlib import Path

import jsonschema
import pytest


def schema() -> dict:
    return json.loads(
        (
            Path(__file__).parents[1] / "python/cppulse/data/project_config.schema.json"
        ).read_bytes()
    )


def test_project_config_schema_is_valid_and_compatible() -> None:
    contract = schema()
    jsonschema.Draft7Validator.check_schema(contract)
    jsonschema.validate(
        {
            "profile": "safety-critical",
            "exclude_paths": ["vendor/**"],
            "rules": {"CPP-CX-001": {"warning_threshold": 20}},
        },
        contract,
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"profile": "unknown"},
        {"rules": {"CPP-CX-001": {"enabled": "false"}}},
        {"execute": "build"},
        {"exclude_paths": "vendor"},
    ],
)
def test_unsupported_config_is_not_silently_ignored(bad: dict) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema())
