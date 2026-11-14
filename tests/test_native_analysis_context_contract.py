"""Additive native parse traces precede normalization into observed contexts."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from cppulse.contracts import load_schema, validate
from cppulse.errors import ContractError


def findings_document() -> dict[str, Any]:
    """Return a minimal old-format report with a complete new parse trace."""
    return {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/selected/repo",
            "analyzed_at": "2026-11-13T12:00:00Z",
            "file_count": 1,
            "total_loc": 1,
            "analysis": {
                "enabled_rules": ["CPP-MEM-001"],
                "parser": {"name": "libclang", "version": "clang version 19.1.7"},
                "files": [
                    {
                        "path": "/selected/repo/main.cpp",
                        "status": "analyzed",
                        "error_count": 0,
                        "compile_context": "database",
                        "parse_arguments": [
                            "-working-directory=/selected/build",
                            "-std=c++17",
                        ],
                        "working_directory": "/selected/repo",
                    }
                ],
            },
        },
        "findings": [],
        "summary": {"total_findings": 0, "by_category": {}, "by_severity": {}},
    }


def assert_valid(document: dict[str, Any]) -> None:
    """Validate both public and installed copies of the prototype contract."""
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1] / "docs/schemas/findings.schema.json"
        ).read_bytes()
    )
    jsonschema.Draft7Validator(schema).validate(document)
    validate("findings", document, version="prototype_v1")
    assert schema == load_schema("findings", version="prototype_v1")


def test_new_parse_trace_is_accepted_by_both_schema_copies() -> None:
    assert_valid(findings_document())


@pytest.mark.parametrize("legacy", ["no_analysis", "old_coverage"])
def test_old_reports_remain_valid_without_parse_traces(legacy: str) -> None:
    document = findings_document()
    if legacy == "no_analysis":
        document["metadata"].pop("analysis")
    else:
        analysis = document["metadata"]["analysis"]
        analysis.pop("parser")
        analysis["files"][0].pop("parse_arguments")
        analysis["files"][0].pop("working_directory")
    assert_valid(document)


def test_argument_order_duplicates_and_empty_strings_are_preserved() -> None:
    document = findings_document()
    arguments = ["-DVALUE=1", "-DVALUE=1", "", "-DVALUE=2"]
    document["metadata"]["analysis"]["files"][0]["parse_arguments"] = arguments
    before = deepcopy(document)
    assert_valid(document)
    assert document == before


@pytest.mark.parametrize("status", ["excluded", "skipped", "failed"])
def test_no_parse_attempt_can_be_recorded_without_invented_arguments(
    status: str,
) -> None:
    document = findings_document()
    item = document["metadata"]["analysis"]["files"][0]
    item.update(
        status=status,
        compile_context="none",
        parse_arguments=None,
        working_directory=None,
    )
    assert_valid(document)


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_parser",
        "empty_version",
        "missing_version",
        "extra_parser",
        "arguments_type",
        "argument_type",
        "cwd_type",
    ],
)
def test_invalid_trace_fields_are_rejected(mutation: str) -> None:
    document = findings_document()
    analysis = document["metadata"]["analysis"]
    item = analysis["files"][0]
    if mutation == "wrong_parser":
        analysis["parser"]["name"] = "some-compiler"
    elif mutation == "empty_version":
        analysis["parser"]["version"] = ""
    elif mutation == "missing_version":
        analysis["parser"].pop("version")
    elif mutation == "extra_parser":
        analysis["parser"]["unproved_target"] = "all"
    elif mutation == "arguments_type":
        item["parse_arguments"] = "-std=c++17"
    elif mutation == "argument_type":
        item["parse_arguments"] = [17]
    else:
        item["working_directory"] = 17
    with pytest.raises(jsonschema.ValidationError):
        schema = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "docs/schemas/findings.schema.json"
            ).read_bytes()
        )
        jsonschema.Draft7Validator(schema).validate(document)
    with pytest.raises(ContractError):
        validate("findings", document, version="prototype_v1")
