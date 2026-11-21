"""Bounded native JSON-schema checks preserve closed-prefix information."""

import hashlib
import io
import json

import jsonschema
import pytest

from cppulse.contracts import load_schema
from cppulse.contracts.validation import _valid_datetime
from cppulse.errors import ContractError


def report():
    return {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/declared/project",
            "analyzed_at": "2026-11-17T00:00:00Z",
            "file_count": 1,
            "total_loc": 1,
        },
        "findings": [
            {
                "rule_id": "CPP-MOD-001",
                "category": "modernization",
                "severity": "info",
                "file": "main.cpp",
                "line": 1,
                "message": "Controlled native fixture",
            }
        ],
        "summary": {
            "total_findings": 1,
            "by_category": {"modernization": 1},
            "by_severity": {"info": 1},
        },
    }


def format_checker():
    """Use the frozen contract's strict timestamp checker, including core installs."""
    checker = jsonschema.FormatChecker()
    checker.checks("date-time", raises=(ValueError, TypeError))(_valid_datetime)
    return checker


def opened(tmp_path, doc):
    from cppulse.native_report_reader import open_native_report

    data = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
    return open_native_report(
        io.BytesIO(data),
        expected_sha256=hashlib.sha256(data).hexdigest(),
        expected_size=len(data),
        directory=tmp_path,
        source_guard=lambda: None,
    )


def test_bounded_reader_keeps_schema_checks_separate_from_native_truth(tmp_path):
    doc = report()
    with opened(tmp_path, doc) as reader:
        assert reader.json_schema_checked is True
        assert reader.native_contract_verified is False
        assert reader.source_verified is False and reader.native_executed is False
        assert reader.analysis_cache_eligible is False
        assert reader.completion.schema_verified is False
        assert list(reader.iter_findings()) == doc["findings"]
        assert reader.document["metadata"] == doc["metadata"]
        assert len(reader.schema_digest) == 64


@pytest.mark.parametrize("mode", ["absent", "present", "root-extra", "metadata-extra"])
def test_valid_optional_and_allowed_extra_shapes_match_eager_schema(tmp_path, mode):
    doc = report()
    if mode == "present":
        doc["metadata"]["analysis"] = {"enabled_rules": [], "files": []}
    if mode == "root-extra":
        doc["allowed-root-extension"] = {"ignored": [1, 2, 3]}
    if mode == "metadata-extra":
        doc["metadata"]["allowed-metadata-extension"] = {}
    jsonschema.Draft7Validator(
        load_schema("findings", "prototype_v1"),
        format_checker=format_checker(),
    ).validate(doc)
    with opened(tmp_path, doc) as reader:
        assert reader.json_schema_checked
        assert list(reader.iter_analysis_files()) == []
        assert ("analysis" in reader.document["metadata"]) == (mode == "present")


@pytest.mark.parametrize(
    "case",
    [
        "empty-analysis",
        "unknown-analysis",
        "empty-metrics",
        "unknown-metrics",
        "missing-root",
        "bad-finding",
        "bad-date",
    ],
)
def test_invalid_closed_or_required_shapes_never_yield_reader(tmp_path, case):
    doc = report()
    if case == "empty-analysis":
        doc["metadata"]["analysis"] = {}
    elif case == "unknown-analysis":
        doc["metadata"]["analysis"] = {"enabled_rules": [], "files": [], "unknown": []}
    elif case == "empty-metrics":
        doc["metadata"]["analysis"] = {
            "enabled_rules": [],
            "files": [],
            "native_metrics": {},
        }
    elif case == "unknown-metrics":
        doc["metadata"]["analysis"] = {
            "enabled_rules": [],
            "files": [],
            "native_metrics": {
                "version": "1.0.0",
                "metric_version": "cppulse-metrics-1",
                "max_token_records": 1,
                "definitions": {"unknown-defined-metric": "1"},
                "files": [],
                "limitations": [],
                "unexpected": [],
            },
        }
    elif case == "missing-root":
        del doc["summary"]
    elif case == "bad-finding":
        doc["findings"][0]["line"] = 0
    elif case == "bad-date":
        doc["metadata"]["analyzed_at"] = "not-a-time"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft7Validator(
            load_schema("findings", "prototype_v1"),
            format_checker=format_checker(),
        ).validate(doc)
    entered = False
    with pytest.raises(ContractError):
        with opened(tmp_path, doc):
            entered = True
    assert entered is False
    assert list(tmp_path.iterdir()) == []


def test_no_whole_report_json_load_or_eager_array_materialization(
    tmp_path, monkeypatch
):
    import cppulse.native_report_reader as module

    doc = report()
    doc["findings"] = [dict(doc["findings"][0], message="x" * 128) for _ in range(1500)]
    doc["summary"]["total_findings"] = 1500
    original = json.loads

    def bounded_load(value, *args, **kwargs):
        if isinstance(value, (bytes, str, bytearray)):
            assert len(value) < 8192, "Whole report was materialized"
        return original(value, *args, **kwargs)

    monkeypatch.setattr(module, "_decode_json", bounded_load)
    with opened(tmp_path, doc) as reader:
        array = reader.document["findings"]
        assert not isinstance(array, list) and len(array) == 1500
        assert sum(1 for _ in reader.iter_findings()) == 1500
        assert array[1499]["message"] == "x" * 128


def test_closed_reader_refuses_replaying_arrays(tmp_path):
    with opened(tmp_path, report()) as reader:
        array = reader.document["findings"]
        iterator = reader.iter_findings()
    with pytest.raises(ContractError):
        next(iterator)
    with pytest.raises(ContractError):
        array[0]


def test_source_guard_failure_after_schema_never_exposes_reader(tmp_path):
    from cppulse.native_report_reader import open_native_report

    data = json.dumps(report()).encode()
    calls = []

    def guard():
        calls.append(1)
        if len(calls) == 3:
            raise ContractError("Source changed during schema check")

    entered = False
    with pytest.raises(ContractError, match="Source changed"):
        with open_native_report(
            io.BytesIO(data),
            expected_sha256=hashlib.sha256(data).hexdigest(),
            expected_size=len(data),
            directory=tmp_path,
            source_guard=guard,
        ):
            entered = True
    assert not entered and len(calls) == 3
    assert list(tmp_path.iterdir()) == []


def test_checked_headers_and_array_binding_cannot_be_mutated_by_caller(tmp_path):
    with opened(tmp_path, report()) as reader:
        copied = reader.document
        copied["metadata"]["file_count"] = 999
        assert reader.document["metadata"]["file_count"] == 1
        with pytest.raises((AttributeError, TypeError)):
            copied["findings"].name = "other-selector"
        with pytest.raises((AttributeError, TypeError)):
            reader.native_contract_verified = True


@pytest.mark.parametrize("bad_call", [1, 2, 3, 4])
@pytest.mark.parametrize("result", [False, True, 0, "unverified"])
def test_non_none_source_guard_is_never_success(tmp_path, bad_call, result):
    from cppulse.native_report_reader import open_native_report

    data = json.dumps(report()).encode()
    calls = []
    entered = False

    def guard():
        calls.append(1)
        return result if len(calls) == bad_call else None

    with pytest.raises(ContractError, match="guard must return None"):
        with open_native_report(
            io.BytesIO(data),
            expected_sha256=hashlib.sha256(data).hexdigest(),
            expected_size=len(data),
            directory=tmp_path,
            source_guard=guard,
        ):
            entered = True
    assert entered == (bad_call == 4)
    assert list(tmp_path.iterdir()) == []


def test_json_schema_check_never_claims_maintenance_contract_parity(tmp_path):
    from cppulse.contracts import validate

    doc = report()
    doc["metadata"]["analysis"] = {
        "enabled_rules": [],
        "files": [
            {
                "path": "main.cpp",
                "status": "analyzed",
                "compile_context": "database",
                "error_count": 0,
            }
        ],
        "native_metrics": {
            "version": "1.0.0",
            "metric_version": "cppulse-metrics-1",
            "max_token_records": 1,
            "definitions": {"physical_loc": "Controlled definition"},
            "files": [],
            "limitations": [],
        },
    }
    jsonschema.Draft7Validator(
        load_schema("findings", "prototype_v1"), format_checker=format_checker()
    ).validate(doc)
    with pytest.raises(ContractError):
        validate("findings", doc, version="prototype_v1")
    with opened(tmp_path, doc) as reader:
        assert reader.json_schema_checked
        assert reader.native_contract_verified is False
