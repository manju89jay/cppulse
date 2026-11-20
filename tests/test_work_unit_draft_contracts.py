"""Draft work-unit document-shape contracts, not runtime scale qualification."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from referencing import Registry, Resource

from cppulse.identities import context_identity

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "docs/schemas/drafts/work_units"
COMMON = "https://schemas.cppulse.local/v2/common.schema.json"


def _artifact(identifier: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "path": identifier + ".json",
        "sha256": "a" * 64,
        "size_bytes": 20,
        "media_type": "application/json",
    }


def _context() -> dict[str, Any]:
    return context_identity(
        {
            "compiler": {"name": "libclang", "version": "synthetic-test-version"},
            "argv": ["-std=c++17"],
            "working_directory": "/synthetic/source",
            "language_standard": "c++17",
            "target": None,
            "provenance": "observed",
            "dependencies": [],
            "limitations": ["Synthetic schema fixture, not executed verification."],
        }
    )


@pytest.fixture
def unit_request() -> dict[str, Any]:
    """Supply one synthetic single-file request using existing v2 identities."""
    return {
        "version": "1.0.0",
        "unit_id": "unit-fixture",
        "source_digest": "a" * 64,
        "primary_file": "include/sample.hpp",
        "primary_sha256": "b" * 64,
        "context": _context(),
        "source_root": "/synthetic/source",
        "work_root": "/synthetic/work/unit-fixture",
        "native": {
            "name": "cppulse-analyzer",
            "version": "synthetic-test-version",
            "sha256": "c" * 64,
        },
        "inputs": {
            name: _artifact(name)
            for name in [
                "source_manifest",
                "selection",
                "configuration",
                "rule_registry",
                "compilation_database",
                "resource_manifest",
            ]
        },
        "dependency_manifest": None,
        "fact_key": None,
        "limits": {
            "wall_seconds": 30,
            "address_space_bytes": 1073741824,
            "cpu_seconds": 20,
            "max_log_bytes": 1048576,
            "max_artifact_bytes": 33554432,
        },
    }


@pytest.fixture
def result() -> dict[str, Any]:
    """Retain a genuine-shaped receipt; the fixture makes no execution claim."""
    return {
        "version": "1.0.0",
        "unit_id": "unit-fixture",
        "request_sha256": "d" * 64,
        "mode": "fresh",
        "outcome": "complete",
        "parse_status": "analyzed",
        "execution_receipt": {
            "version": "2.0.0",
            "id": "receipt-fixture",
            "source_digest": "a" * 64,
            "context_id": "invocation-context-fixture",
            "producer": {
                "name": "cppulse.execution",
                "version": "synthetic-test-version",
            },
            "argv": ["/synthetic/cppulse-analyzer", "--repo", "/synthetic/source"],
            "cwd": "/synthetic/source",
            "status": "passed",
            "reason": "Synthetic structural fixture only.",
            "exit_code": 0,
            "signal": None,
            "started_at": "2026-11-14T10:00:00Z",
            "finished_at": "2026-11-14T10:00:01Z",
            "artifact_ids": ["native-report"],
            "log_artifact_ids": [],
            "depends_on": [],
        },
        "cache_origin": None,
        "artifacts": [_artifact("native-report")],
        "limits_applied": {
            "wall_time": True,
            "address_space": True,
            "cpu_time": True,
            "output_bytes": True,
        },
        "measurements": {
            "wall_seconds": 1.0,
            "cpu_seconds": None,
            "peak_memory_bytes": None,
            "peak_memory_scope": None,
            "measurement_method": None,
        },
        "reason": "Synthetic structural fixture; no process executed by this test.",
        "limitations": [
            "Resource and freshness semantics require runtime acceptance tests."
        ],
    }


def _validator(name: str) -> jsonschema.Draft7Validator:
    schema = json.loads((DRAFTS / (name + ".schema.json")).read_text())
    jsonschema.Draft7Validator.check_schema(schema)
    schemas = [
        json.loads(path.read_text())
        for directory in [ROOT / "python/cppulse/contracts/schemas/v2", DRAFTS]
        for path in directory.glob("*.schema.json")
    ]
    registry = Registry().with_resources(
        (item["$id"], Resource.from_contents(item)) for item in schemas
    )
    return jsonschema.Draft7Validator(
        schema, registry=registry, format_checker=jsonschema.FormatChecker()
    )


def test_request_reuses_v2_context_and_artifact_shapes(
    unit_request: dict[str, Any]
) -> None:
    _validator("work_request").validate(unit_request)


@pytest.mark.parametrize("value", [0, -1, True, "30", None])
def test_request_rejects_unusable_wall_bounds(
    unit_request: dict[str, Any], value: Any
) -> None:
    unit_request["limits"]["wall_seconds"] = value
    with pytest.raises(jsonschema.ValidationError):
        _validator("work_request").validate(unit_request)


@pytest.mark.parametrize(
    "path",
    [
        "../sample.hpp",
        "/sample.hpp",
        "a/../../b.cpp",
        "C:/a.cpp",
        "a\\b.cpp",
        ".",
        "a/./b.cpp",
        "a//b.cpp",
        "a/",
        "a.cpp\n",
    ],
)
def test_request_rejects_escaping_primary_paths(
    unit_request: dict[str, Any], path: str
) -> None:
    unit_request["primary_file"] = path
    with pytest.raises(jsonschema.ValidationError):
        _validator("work_request").validate(unit_request)


def test_request_rejects_unknown_execution_options(
    unit_request: dict[str, Any]
) -> None:
    unit_request["shell_command"] = "some project command"
    with pytest.raises(jsonschema.ValidationError):
        _validator("work_request").validate(unit_request)


def test_result_accepts_explicit_unknown_resource_measurements(
    result: dict[str, Any]
) -> None:
    _validator("work_result").validate(result)


def test_cache_reuse_cannot_claim_a_new_native_execution(
    result: dict[str, Any]
) -> None:
    result["mode"] = "reused"
    result["cache_origin"] = {
        "run_id": "origin-run",
        "manifest_sha256": "b" * 64,
        "artifact": _artifact("original-native-facts"),
        "fact_key": "c" * 64,
        "original_source_digest": "a" * 64,
    }
    with pytest.raises(jsonschema.ValidationError):
        _validator("work_result").validate(result)
    result["execution_receipt"] = None
    _validator("work_result").validate(result)


def test_cached_partial_results_cannot_be_positive_hits(result: dict[str, Any]) -> None:
    result["mode"] = "reused"
    result["execution_receipt"] = None
    result["cache_origin"] = {
        "run_id": "origin-run",
        "manifest_sha256": "b" * 64,
        "artifact": _artifact("original-native-facts"),
        "fact_key": "c" * 64,
        "original_source_digest": "a" * 64,
    }
    result["parse_status"] = "partial"
    with pytest.raises(jsonschema.ValidationError):
        _validator("work_result").validate(result)


def test_fresh_attempt_cannot_substitute_cache_origin_for_receipt(
    result: dict[str, Any]
) -> None:
    result["execution_receipt"] = None
    with pytest.raises(jsonschema.ValidationError):
        _validator("work_result").validate(result)


def test_cache_entry_requires_complete_dependency_identity() -> None:
    entry = {
        "version": "1.0.0",
        "fact_key": "a" * 64,
        "unit_id": "unit-fixture",
        "state": "complete",
        "primary_file": "include/sample.hpp",
        "primary_sha256": "b" * 64,
        "context_digest": "c" * 64,
        "native_sha256": "d" * 64,
        "registry_sha256": "e" * 64,
        "extraction_configuration_sha256": "f" * 64,
        "dependency_manifest": _artifact("dependencies"),
        "dependencies_complete": True,
        "origin": {
            "run_id": "origin-run",
            "manifest_sha256": "a" * 64,
            "source_digest": "b" * 64,
        },
        "artifacts": [_artifact("facts")],
        "created_at": "2026-11-14T10:00:00Z",
        "limitations": [
            "Synthetic cache fixture; integrity/authenticity are not established by schema."
        ],
    }
    _validator("cache_entry").validate(entry)
    entry["dependencies_complete"] = False
    with pytest.raises(jsonschema.ValidationError):
        _validator("cache_entry").validate(entry)


def test_cursor_pins_run_query_sort_and_bounded_page_size() -> None:
    cursor = {
        "version": "1.0.0",
        "run_id": "run-fixture",
        "manifest_sha256": "a" * 64,
        "query_sha256": "b" * 64,
        "sort": "file-context-rule-location-occurrence-id",
        "page_size": 100,
        "after": {
            "file": "include/sample.hpp",
            "context_id": "context-fixture",
            "rule_id": "cppulse.CPP-MEM-001",
            "line": 5,
            "column": 1,
            "occurrence": 0,
            "observation_id": "finding-fixture",
        },
    }
    _validator("query_cursor").validate(cursor)
    for field in ["manifest_sha256", "query_sha256", "run_id"]:
        candidate = deepcopy(cursor)
        del candidate[field]
        with pytest.raises(jsonschema.ValidationError):
            _validator("query_cursor").validate(candidate)
    cursor["page_size"] = 100000
    with pytest.raises(jsonschema.ValidationError):
        _validator("query_cursor").validate(cursor)
