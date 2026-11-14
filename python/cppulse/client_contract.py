"""Advertise supported public client interfaces without probing the workspace."""

from __future__ import annotations

from importlib import resources
import json
from typing import Any

import jsonschema

from cppulse import __version__


def capabilities() -> dict[str, Any]:
    """Return a versioned editor/agent negotiation document without execution.

    This describes interface availability. It does not attest native runtime,
    installed extras, project verification or the consumer's environment.
    """
    result = {
        "contract_version": "1.0.0",
        "tool_version": __version__,
        "snapshot_view_versions": ["2.0.0"],
        "sarif_versions": ["2.1.0"],
        "sarif_column_kinds": ["unicodeCodePoints"],
        "commands": [
            "capabilities",
            "doctor",
            "init",
            "config",
            "analyze",
            "watch",
            "report",
            "collect",
            "assess",
            "check",
            "explain",
            "baseline",
            "export-sarif",
            "compare",
            "diagnostics",
            "serve",
            "scaffold",
        ],
        "execution_on_open": False,
    }
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas/install_v1/client_capabilities.schema.json")
        .read_bytes()
    )
    jsonschema.Draft7Validator.check_schema(schema)
    jsonschema.validate(result, schema)
    return result
