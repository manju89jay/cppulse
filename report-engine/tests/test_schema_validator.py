"""Tests for schema_validator module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.schema_validator import load_schema, validate_document, validate_file

# ---------------------------------------------------------------------------
# load_schema
# ---------------------------------------------------------------------------


def test_load_schema_findings() -> None:
    """load_schema returns a dict for findings schema."""
    schema = load_schema("findings")
    assert isinstance(schema, dict)
    assert schema.get("title") == "cppulse Static Analysis Findings"


def test_load_schema_git_metrics() -> None:
    """load_schema returns a dict for git_metrics schema."""
    schema = load_schema("git_metrics")
    assert isinstance(schema, dict)
    assert "file_metrics" in schema["properties"]


def test_load_schema_risk_scores() -> None:
    """load_schema returns a dict for risk_scores schema."""
    schema = load_schema("risk_scores")
    assert "health_score" in schema["properties"]


def test_load_schema_roadmap() -> None:
    """load_schema returns a dict for roadmap schema."""
    schema = load_schema("roadmap")
    assert "items" in schema["properties"]


def test_load_schema_unknown_raises() -> None:
    """load_schema raises KeyError for unknown schema names."""
    with pytest.raises(KeyError, match="Unknown schema"):
        load_schema("nonexistent_schema")


# ---------------------------------------------------------------------------
# validate_document
# ---------------------------------------------------------------------------


def test_validate_document_valid_findings(data_dir: Path) -> None:
    """validate_document returns empty list for valid findings data."""
    import json

    findings_path = data_dir / "findings.json"
    data = json.loads(findings_path.read_text())
    errors = validate_document(data, "findings")
    assert errors == []


def test_validate_document_invalid_findings() -> None:
    """validate_document returns errors for invalid data."""
    bad_data = {"version": "1.0.0"}  # missing required fields
    errors = validate_document(bad_data, "findings")
    assert len(errors) > 0


def test_validate_document_unknown_schema() -> None:
    """validate_document returns error message for unknown schema."""
    errors = validate_document({}, "bad_schema")
    assert len(errors) == 1
    assert "Unknown schema" in errors[0]


def test_validate_document_valid_roadmap(data_dir: Path) -> None:
    """validate_document returns empty list for valid roadmap data."""
    roadmap_path = data_dir / "roadmap.json"
    data = json.loads(roadmap_path.read_text())
    errors = validate_document(data, "roadmap")
    assert errors == []


# ---------------------------------------------------------------------------
# validate_file
# ---------------------------------------------------------------------------


def test_validate_file_valid(data_dir: Path) -> None:
    """validate_file returns empty list for valid file."""
    errors = validate_file(data_dir / "findings.json", "findings")
    assert errors == []


def test_validate_file_missing(tmp_path: Path) -> None:
    """validate_file raises FileNotFoundError for missing file."""
    with pytest.raises(FileNotFoundError):
        validate_file(tmp_path / "nonexistent.json", "findings")


def test_validate_file_bad_json(tmp_path: Path) -> None:
    """validate_file raises JSONDecodeError for malformed JSON."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        validate_file(bad_file, "findings")
