"""Private request checks for a selected-artifact derived query index.

These checks do not read a store, build an index or validate any source report.
The public paging and transactional producer gates remain separate.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any

import jsonschema

from cppulse.contracts.frozen_input import _EXACT_INTEGER_VALIDATOR
from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes


def validate_index_request(document: dict[str, Any]) -> None:
    """Validate closed fields, exact integer budgets and canonical paths."""
    schema = json.loads(
        (
            Path(__file__).with_name("schemas")
            / "result_index_private/request.schema.json"
        ).read_bytes()
    )
    try:
        _EXACT_INTEGER_VALIDATOR(schema).validate(document)
        if (
            re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", document["source"]["run_id"]
            )
            is None
        ):
            raise ValueError("Index run ID is not canonical")
        if (
            re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", document["source"]["artifact_id"]
            )
            is None
        ):
            raise ValueError("Index artifact ID is not canonical")
        for key, value in document["source"].items():
            if not isinstance(value, str):
                continue
            encoded = value.encode("utf-8", errors="strict")
            if "\0" in value or len(encoded) > (
                4096 if key == "artifact_path" else 256
            ):
                raise ValueError("Index identity exceeds its UTF-8 boundary")
        path = document["source"]["artifact_path"]
        selected = PurePosixPath(path)
        if (
            selected.is_absolute()
            or PureWindowsPath(path).drive
            or path == "."
            or ".." in selected.parts
            or "\\" in path
            or str(selected) != path
        ):
            raise ValueError("Index artifact path must be canonical and relative")
        if len(canonical_json_bytes(document)) > 16 * 1024:
            raise ValueError("Index request exceeds its metadata budget")
    except (jsonschema.ValidationError, ValueError, TypeError, UnicodeError) as error:
        raise ContractError("Invalid selected-artifact index request") from error
