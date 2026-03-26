"""Schema validation for cppulse report-engine JSON inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema


SCHEMAS_DIR = Path(__file__).parent.parent.parent / "docs" / "schemas"

SCHEMA_FILES: dict[str, str] = {
    "findings": "findings.schema.json",
    "git_metrics": "git_metrics.schema.json",
    "risk_scores": "risk_scores.schema.json",
    "roadmap": "roadmap.schema.json",
}


def load_schema(schema_name: str) -> dict[str, Any]:
    """Load a JSON schema by name.

    Args:
        schema_name: One of 'findings', 'git_metrics', 'risk_scores', 'roadmap'.

    Returns:
        The parsed JSON schema as a dict.

    Raises:
        KeyError: If schema_name is not recognized.
        FileNotFoundError: If the schema file does not exist.
    """
    if schema_name not in SCHEMA_FILES:
        raise KeyError(f"Unknown schema: {schema_name!r}. Valid: {list(SCHEMA_FILES)}")
    schema_path = SCHEMAS_DIR / SCHEMA_FILES[schema_name]
    with schema_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)  # type: ignore[no-any-return]


def validate_document(data: dict[str, Any], schema_name: str) -> list[str]:
    """Validate a data document against the named schema.

    Args:
        data: Parsed JSON data to validate.
        schema_name: One of 'findings', 'git_metrics', 'risk_scores', 'roadmap'.

    Returns:
        A list of validation error messages. Empty list means valid.
    """
    try:
        schema = load_schema(schema_name)
    except (KeyError, FileNotFoundError) as exc:
        return [str(exc)]

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    return [e.message for e in errors]


def validate_file(file_path: Path, schema_name: str) -> list[str]:
    """Validate a JSON file against the named schema.

    Args:
        file_path: Path to the JSON file to validate.
        schema_name: One of 'findings', 'git_metrics', 'risk_scores', 'roadmap'.

    Returns:
        A list of validation error messages. Empty list means valid.

    Raises:
        FileNotFoundError: If file_path does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    with file_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return validate_document(data, schema_name)
