"""Tests for src/schema_validator.py — SchemaValidator."""

from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest

from src.schema_validator import SchemaValidator

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "schemas"
    / "git_metrics.schema.json"
)


def _valid_payload() -> dict:
    """Return a minimal valid git_metrics payload."""
    return {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/tmp/repo",
            "analyzed_at": "2025-01-15T12:00:00+00:00",
            "commit_range": "abc12345..def67890",
            "total_commits": 10,
        },
        "file_metrics": [
            {
                "file": "main.cpp",
                "change_frequency": 5,
                "unique_contributors": 2,
                "age_days": 30,
                "lines_of_code": 100,
            }
        ],
        "knowledge_silos": [],
    }


class TestSchemaValidatorInit:
    """SchemaValidator initialisation."""

    def test_loads_default_schema(self) -> None:
        """Constructor succeeds when the default schema file exists."""
        validator = SchemaValidator()
        assert validator is not None

    def test_custom_schema_path(self, tmp_path: Path) -> None:
        """Constructor accepts a custom schema path."""
        # Copy the real schema to a tmp location
        schema_content = _SCHEMA_PATH.read_text()
        custom = tmp_path / "custom_schema.json"
        custom.write_text(schema_content)
        validator = SchemaValidator(schema_path=custom)
        assert validator is not None

    def test_missing_schema_raises(self, tmp_path: Path) -> None:
        """FileNotFoundError is raised when schema file does not exist."""
        missing = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            SchemaValidator(schema_path=missing)


class TestSchemaValidatorValidate:
    """SchemaValidator.validate() method."""

    def test_valid_payload_passes(self) -> None:
        """validate() does not raise for a valid payload."""
        validator = SchemaValidator()
        validator.validate(_valid_payload())  # should not raise

    def test_missing_version_raises(self) -> None:
        """ValidationError is raised when 'version' key is absent."""
        payload = _valid_payload()
        del payload["version"]
        validator = SchemaValidator()
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(payload)

    def test_missing_metadata_raises(self) -> None:
        """ValidationError is raised when 'metadata' key is absent."""
        payload = _valid_payload()
        del payload["metadata"]
        validator = SchemaValidator()
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(payload)

    def test_wrong_version_raises(self) -> None:
        """ValidationError is raised when version string does not match const."""
        payload = _valid_payload()
        payload["version"] = "2.0.0"
        validator = SchemaValidator()
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(payload)

    def test_missing_file_metrics_raises(self) -> None:
        """ValidationError is raised when 'file_metrics' key is absent."""
        payload = _valid_payload()
        del payload["file_metrics"]
        validator = SchemaValidator()
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(payload)

    def test_missing_knowledge_silos_raises(self) -> None:
        """ValidationError is raised when 'knowledge_silos' key is absent."""
        payload = _valid_payload()
        del payload["knowledge_silos"]
        validator = SchemaValidator()
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(payload)


class TestSchemaValidatorIsValid:
    """SchemaValidator.is_valid() method."""

    def test_valid_payload_returns_true(self) -> None:
        """is_valid() returns True for a conforming payload."""
        validator = SchemaValidator()
        assert validator.is_valid(_valid_payload()) is True

    def test_invalid_payload_returns_false(self) -> None:
        """is_valid() returns False (no exception) for a non-conforming payload."""
        payload = _valid_payload()
        del payload["version"]
        validator = SchemaValidator()
        assert validator.is_valid(payload) is False

    def test_empty_dict_returns_false(self) -> None:
        """is_valid() returns False for an empty dictionary."""
        validator = SchemaValidator()
        assert validator.is_valid({}) is False

    def test_full_payload_with_silo_returns_true(self) -> None:
        """is_valid() returns True for a payload that includes a silo entry."""
        payload = _valid_payload()
        payload["knowledge_silos"] = [
            {
                "file": "legacy.cpp",
                "sole_contributor": "Alice",
                "last_commit_date": "2025-01-01",
                "risk_note": "Bus factor: 1.",
            }
        ]
        validator = SchemaValidator()
        assert validator.is_valid(payload) is True
