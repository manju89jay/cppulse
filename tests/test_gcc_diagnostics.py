"""Synthetic GCC JSON transformations; actual compiler execution is separate."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

import pytest

from cppulse.adapters.gcc_diagnostics import GccDiagnostics, parse_gcc_json
from cppulse.errors import ContractError

PRODUCER = {"name": "GNU-G++", "version": "14.2.0"}


def diagnostic() -> dict[str, Any]:
    """Return a labeled synthetic instance of the documented GCC JSON shape."""
    return {
        "kind": "warning",
        "message": "unused variable 'value'",
        "option": "-Wunused-variable",
        "locations": [
            {
                "caret": {
                    "file": "/project/src/main.cpp",
                    "line": 2,
                    "byte-column": 7,
                    "display-column": 9,
                    "column": 9,
                }
            }
        ],
        "children": [],
    }


def parse(records: list[dict[str, Any]]) -> GccDiagnostics:
    return parse_gcc_json(
        json.dumps(records).encode(),
        source_root="/project",
        scope_files=["src/main.cpp"],
        producer=PRODUCER,
    )


def test_locations_use_explicit_byte_columns_and_repository_identity() -> None:
    report = parse([diagnostic()])
    assert report.usability == "usable"
    row = report.diagnostics[0]
    assert (row.file, row.line, row.column) == ("src/main.cpp", 2, 7)
    assert row.namespaced_rule_id == "gcc:-Wunused-variable"
    assert row.rule_version == "14.2.0"
    assert report.origin == "import"


def test_repeated_occurrences_and_child_notes_are_retained() -> None:
    row = diagnostic()
    note = deepcopy(row)
    note.update(kind="note", message="declared here")
    note.pop("option")
    row["children"] = [note]
    report = parse([row, diagnostic()])
    assert len(report.diagnostics) == 3
    assert report.diagnostics[0].fingerprint == report.diagnostics[2].fingerprint
    assert report.diagnostics[1].severity == "info"


def test_unsafe_rule_spelling_has_collision_resistant_namespace() -> None:
    row = diagnostic()
    row["option"] = "-Wformat=odd value"
    item = parse([row]).diagnostics[0]
    assert item.original_rule_id == row["option"]
    assert item.namespaced_rule_id.startswith("gcc:option-")
    assert len(item.namespaced_rule_id) == len("gcc:option-") + 64


def test_unknown_byte_column_does_not_guess_a_display_column() -> None:
    row = diagnostic()
    row["locations"][0]["caret"].pop("byte-column")
    assert parse([row]).diagnostics[0].column is None


@pytest.mark.parametrize("raw", [b"{}", b"not JSON", b"[NaN]", b"\xff"])
def test_malformed_reports_are_not_clean(raw: bytes) -> None:
    report = parse_gcc_json(
        raw, source_root="/project", scope_files=["src/main.cpp"], producer=PRODUCER
    )
    assert report.usability == "malformed"
    assert report.diagnostics == ()
    assert report.report_sha256 and report.size_bytes == len(raw)


@pytest.mark.parametrize(
    "change",
    [
        "outside",
        "traversal",
        "windows",
        "unlocated",
        "line",
        "column",
        "kind",
        "kind-list",
        "kind-dict",
        "children",
    ],
)
def test_unsupported_location_or_shape_never_invents_a_finding(change: str) -> None:
    row = diagnostic()
    caret = row["locations"][0]["caret"]
    if change == "outside":
        caret["file"] = "/project-other/src/main.cpp"
    elif change == "traversal":
        caret["file"] = "../main.cpp"
    elif change == "windows":
        caret["file"] = "C:\\src\\main.cpp"
    elif change == "unlocated":
        row["locations"] = []
    elif change == "line":
        caret["line"] = True
    elif change == "column":
        caret["byte-column"] = 0
    elif change == "kind":
        row["kind"] = "future-special"
    elif change == "kind-list":
        row["kind"] = []
    elif change == "kind-dict":
        row["kind"] = {}
    else:
        row["children"] = "not a diagnostic array"
    report = parse([row])
    assert report.usability == "unsupported"
    assert report.diagnostics == ()
    assert report.limitations


def test_empty_log_and_empty_valid_array_remain_distinct() -> None:
    absent = parse_gcc_json(
        b"", source_root="/project", scope_files=["src/main.cpp"], producer=PRODUCER
    )
    assert absent.usability == "missing"
    empty = parse([])
    assert empty.usability == "usable" and empty.diagnostics == ()
    assert any("complete" in line.lower() for line in empty.limitations)


def test_unknown_producer_version_is_explicitly_unavailable() -> None:
    report = parse_gcc_json(
        b"[]",
        source_root="/project",
        scope_files=["src/main.cpp"],
        producer={"name": "GNU-G++", "version": "99.0"},
    )
    assert report.usability == "unsupported"


def test_parser_limits_and_invalid_declared_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cppulse.adapters.gcc_diagnostics as module

    monkeypatch.setattr(module, "MAX_REPORT_BYTES", 1)
    assert parse([]).usability == "unsupported"
    with pytest.raises(ContractError):
        parse_gcc_json(b"[]", source_root="/project", scope_files=["../secret.cpp"])


def test_missing_producer_version_is_not_invented() -> None:
    report = parse_gcc_json(b"[]", source_root="/project", scope_files=["src/main.cpp"])
    assert report.usability == "unsupported"
    assert report.producer_version != "14.2.0"


def test_duplicate_json_fields_are_malformed() -> None:
    raw = (
        json.dumps([diagnostic()])
        .replace('"kind": "warning"', '"kind": "warning", "kind": "note"')
        .encode()
    )
    report = parse_gcc_json(
        raw, source_root="/project", scope_files=["src/main.cpp"], producer=PRODUCER
    )
    assert report.usability == "malformed"


def test_invalid_root_type_is_a_contract_error() -> None:
    with pytest.raises(ContractError):
        parse_gcc_json(
            b"[]", source_root=None, scope_files=["src/main.cpp"], producer=PRODUCER
        )
