"""Schema validation module for cppulse predictor outputs.

Validates risk_scores.json and roadmap.json against their JSON schemas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from cppulse.contracts import load_schema


class SchemaValidator:
    """Validates predictor output against JSON schemas.

    Raises ValidationError if the data does not conform to the schema.
    """

    def __init__(self, schema_dir: Path | None = None) -> None:
        """Load packaged schemas, or explicit caller-supplied schema files."""
        if schema_dir is None:
            self._risk_scores_schema = load_schema("risk_scores", "prototype_v1")
            self._roadmap_schema = load_schema("roadmap", "prototype_v1")
        else:
            self._risk_scores_schema = self._load_schema(
                Path(schema_dir) / "risk_scores.schema.json"
            )
            self._roadmap_schema = self._load_schema(
                Path(schema_dir) / "roadmap.schema.json"
            )

    def validate_risk_scores(self, data: dict[str, Any]) -> None:
        """Validate risk_scores.json data against the schema.

        Args:
            data: Parsed risk scores dict to validate.

        Raises:
            jsonschema.ValidationError: If data does not match the schema.
            jsonschema.SchemaError: If the schema itself is malformed.
        """
        jsonschema.validate(instance=data, schema=self._risk_scores_schema)

    def validate_roadmap(self, data: dict[str, Any]) -> None:
        """Validate roadmap.json data against the schema.

        Args:
            data: Parsed roadmap dict to validate.

        Raises:
            jsonschema.ValidationError: If data does not match the schema.
            jsonschema.SchemaError: If the schema itself is malformed.
        """
        jsonschema.validate(instance=data, schema=self._roadmap_schema)

    @staticmethod
    def _load_schema(schema_path: Path) -> dict[str, Any]:
        """Load and parse a JSON schema file.

        Args:
            schema_path: Absolute path to the .schema.json file.

        Returns:
            Parsed schema dict.

        Raises:
            FileNotFoundError: If schema_path does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        with schema_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
