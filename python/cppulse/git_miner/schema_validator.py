"""JSON schema validator for git_metrics output.

Validates the git_metrics output dictionary against the canonical schema
shipped with the cppulse contracts package.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema

from cppulse.contracts import load_schema

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validates git_metrics output against a JSON schema.

    Args:
        schema_path: Path to the JSON schema file. Defaults to the canonical
                     packaged prototype_v1 schema.
    """

    def __init__(self, schema_path: Path | None = None) -> None:
        """Initialize SchemaValidator.

        Args:
            schema_path: Optional override for the schema file path.

        Raises:
            FileNotFoundError: If the schema file does not exist.
        """
        if schema_path is None:
            self._schema = load_schema("git_metrics", "prototype_v1")
            logger.debug("Loaded packaged Git metrics schema")
        else:
            resolved = Path(schema_path)
            if not resolved.exists():
                raise FileNotFoundError(f"Schema file not found: {resolved}")
            with resolved.open("r", encoding="utf-8") as source:
                self._schema = json.load(source)
            logger.debug("Loaded schema from %s", resolved)

    def validate(self, data: dict[str, Any]) -> None:
        """Validate data against the loaded JSON schema.

        Args:
            data: The dictionary to validate (typically the full git_metrics
                  output payload).

        Raises:
            jsonschema.ValidationError: If the data does not conform to the schema.
        """
        jsonschema.validate(instance=data, schema=self._schema)
        logger.debug("Schema validation passed")

    def is_valid(self, data: dict[str, Any]) -> bool:
        """Return True if data is valid, False otherwise (no exception raised).

        Args:
            data: The dictionary to validate.

        Returns:
            True when valid, False when a validation error would occur.
        """
        try:
            self.validate(data)
            return True
        except jsonschema.ValidationError as exc:
            logger.warning("Schema validation failed: %s", exc.message)
            return False
