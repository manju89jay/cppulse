"""Genuine LLVM 19.1.7 samples and opt-in real public collector journeys.

The serialized samples bind exact source/argv/tool bytes and retain clean-control
execution receipts. Empty text is still a missing import, never a clean fact.
Set CPPULSE_TIDY19_TOOL to the exact qualified executable for live public checks;
missing access is an explicit skip, not evidence that those checks passed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from cppulse.adapters.external_analyzers import parse_clang_tidy_text
from cppulse.contracts import validate
from cppulse.identities import context_identity
from cppulse.presentation import build_snapshot_view, render_snapshot_html
from cppulse.run_store import RunStore
from cppulse.workflows import collect_request
from test_collection import documents
from test_public_workflows import request_for

FIXTURES = Path(__file__).parent / "fixtures/clang_tidy19_qualification"
CASES = json.loads((FIXTURES / "cases.json").read_text())
RECEIPT = json.loads((FIXTURES / "producer-receipt.json").read_text())
TOOL_SHA256 = "9ebd2c4f2a123c058f4744e9a02a8000ab9ba22f9b835958dfda7c4d7de2527c"
PRODUCER = {"name": "clang-tidy", "version": "19.1.7"}
LOCATIONS = {
    "move-positive": (16, 10),
    "move-correlated-condition": (39, 29),
    "dangling-temporary-owner": (7, 27),
    "unused-ignored-function": (12, 3),
    "unused-void-default": (16, 9),
    "unused-void-false": (16, 9),
    "unused-ignored-type": (22, 3),
}


def test_genuine_capture_identity_source_and_artifact_pins() -> None:
    """Changing any producer sample/source requires genuine new qualification."""
    assert RECEIPT["tool_sha256"] == TOOL_SHA256
    assert RECEIPT["producer"] == PRODUCER and RECEIPT["checks_passed"] is True
    assert (
        RECEIPT["fixture_manifest_sha256"]
        == hashlib.sha256((FIXTURES / "cases.json").read_bytes()).hexdigest()
    )
    assert len(RECEIPT["cases"]) == len(CASES["cases"]) == 16
    assert {row["check"] for row in CASES["cases"]} == {
        "bugprone-use-after-move",
        "bugprone-dangling-handle",
        "bugprone-unused-return-value",
    }
    for name, digest in RECEIPT["source_files"].items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest
    for artifact in RECEIPT["captured_artifacts"]:
        raw = (FIXTURES / artifact["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == artifact["sha256"]
        assert len(raw) == artifact["bytes"]
    assert all(command["exit_code"] == 0 for command in RECEIPT["commands"])


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda case: case["id"])
def test_actual_diagnostic_locations_notes_and_clean_control_boundaries(
    case: dict[str, Any],
) -> None:
    """Real positive locations/notes survive; clean stdout stays a missing import."""
    raw = (FIXTURES / "captured" / (case["id"] + ".stdout")).read_bytes()
    report = parse_clang_tidy_text(
        raw,
        source_root=RECEIPT["captured_source_root"],
        scope_files=[case["source"]],
        producer=PRODUCER,
    )
    assert report.origin == "import"
    assert len(report.diagnostics) == case["expected_occurrences"]
    assert report.report_sha256 == hashlib.sha256(raw).hexdigest()
    if case["expected_occurrences"]:
        assert report.usability == "usable"
        row = report.diagnostics[0]
        assert row.original_rule_id == case["check"]
        assert row.namespaced_rule_id == "clang-tidy:" + case["check"]
        assert row.rule_version == "19.1.7" and row.file == case["source"]
        assert (row.line, row.column) == LOCATIONS[case["id"]]
        assert len(row.fingerprint) == 64
        if b": note:" in raw:
            assert any("Secondary notes" in value for value in report.limitations)
    else:
        assert raw == b"" and report.usability == "missing"
        assert any("missing is not zero findings" in x for x in report.limitations)


def test_actual_default_options_and_explicit_void_cast_controls() -> None:
    """This is clang-tidy's default, unlike ordinary nodiscard diagnostics."""
    unused = (
        FIXTURES / "captured/defaults-bugprone-unused-return-value.stdout"
    ).read_text()
    dangling = (
        FIXTURES / "captured/defaults-bugprone-dangling-handle.stdout"
    ).read_text()
    assert "bugprone-unused-return-value.AllowCastToVoid: 'false'" in unused
    assert (
        "bugprone-dangling-handle.HandleClasses: "
        "'std::basic_string_view;std::experimental::basic_string_view'"
    ) in dangling
    cases = {case["id"]: case for case in CASES["cases"]}
    option = "bugprone-unused-return-value.AllowCastToVoid"
    assert option not in cases["unused-void-default"]["options"]
    assert cases["unused-void-default"]["expected_occurrences"] == 1
    assert cases["unused-void-false"]["options"][option] is False
    assert cases["unused-void-true"]["options"][option] is True
    assert cases["unused-void-true"]["expected_occurrences"] == 0
    assert "not path-sensitive" in cases["move-correlated-condition"]["limitation"]
    assert "outside" in cases["move-member-global"]["limitation"]
    assert (
        "arbitrary custom-handle or span"
        in cases["dangling-custom-default"]["limitation"]
    )


def _live_request(workspace: Path, case: dict[str, Any], tool: Path) -> dict[str, Any]:
    """Reuse the existing public request fixture and real collector contracts."""
    request = request_for(workspace, "print('unused declaration helper')")
    (workspace / "source.cpp").write_bytes((FIXTURES / case["source"]).read_bytes())
    request["source"].update(
        files=["source.cpp"],
        inventory_complete=False,
        limitations=[
            "Controlled selected source; system headers/runtime dependencies are not a closed bundle."
        ],
    )
    compiler = Path("/usr/bin/g++-14")
    assert (
        compiler.is_file()
    ), "The declared GCC14 context is required; no silent replacement"
    resource = Path(
        os.environ.get(
            "CPPULSE_CLANG_RESOURCE_DIR",
            "/workspace/cppulse/work/native-deps/usr/lib/llvm-19/lib/clang/19",
        )
    ).resolve(strict=True)
    assert (resource / "include/stddef.h").is_file()
    argv = [
        str(tool),
        "source.cpp",
        "--quiet",
        "--checks=-*," + case["check"],
        "--config="
        + json.dumps(
            {"Checks": "-*," + case["check"], "CheckOptions": case["options"]}
        ),
        "--",
        "-std=c++17",
        "-D" + case["macro"],
        "-Wno-dangling-gsl",
        "-resource-dir=" + str(resource),
    ]
    build_argv = [
        str(compiler),
        "-std=c++17",
        "-D" + case["macro"],
        "-c",
        "source.cpp",
        "-o",
        "main.o",
    ]
    request["contexts"] = [
        context_identity(
            {
                "id": name,
                "compiler": {"name": producer, "version": version},
                "argv": arguments,
                "working_directory": str(workspace),
                "language_standard": "c++17",
                "target": None,
                "provenance": "inferred",
                "dependencies": [],
                "limitations": [
                    "Declared finite context; original imported diagnostic identity is not producer authentication."
                ],
            }
        )
        for name, producer, version, arguments in [
            ("local", "GNU-G++", "14.2.0", build_argv),
            ("tidy-context", "clang", "19.1.7", argv),
        ]
    ]
    plan = request["plan"]
    plan["recipe"]["contexts"] = ["local", "tidy-context"]
    build = plan["recipe"]["steps"][0]
    build.update(
        argv=build_argv,
        inputs=["source.cpp"],
        outputs=["main.o"],
        depends_on=["tidy"],
        timeout_seconds=30,
    )
    plan["recipe"]["steps"] = [
        {
            "id": "tidy-version",
            "context_id": "tidy-context",
            "argv": [str(tool), "--version"],
            "cwd": ".",
            "depends_on": [],
            "inputs": [],
            "outputs": [],
            "timeout_seconds": 15,
        },
        {
            "id": "tidy",
            "context_id": "tidy-context",
            "argv": argv,
            "cwd": ".",
            "depends_on": ["tidy-version"],
            "inputs": ["source.cpp"],
            "outputs": [],
            "timeout_seconds": 30,
        },
        build,
    ]
    plan["bindings"][0].update(scope_files=["source.cpp"], exercised_inputs=["main.o"])
    plan["limits"].update(max_log_bytes=16384)
    request["normalizers"] = [
        {
            "id": "selected-tidy",
            "kind": "external_import",
            "normalizer_version": "1.0.0",
            "report": {"step_id": "tidy", "role": "stdout", "path": None},
            "context_id": "tidy-context",
            "source_root": str(workspace),
            "scope_files": ["source.cpp"],
            "producer": PRODUCER,
            "adapter": "clang-tidy-text",
        }
    ]
    return request


@pytest.mark.parametrize(
    "case_id",
    [
        "move-positive",
        "dangling-temporary-owner",
        "unused-ignored-function",
        "unused-void-true",
    ],
)
def test_public_collector_actual_tool_preserves_import_and_report_boundaries(
    tmp_path: Path, case_id: str
) -> None:
    """Explicit real tool execution never upgrades normalized imported claims."""
    selection = os.environ.get("CPPULSE_TIDY19_TOOL")
    if not selection:
        pytest.skip("Set CPPULSE_TIDY19_TOOL for required live 19.1.7 qualification")
    tool = Path(selection).resolve(strict=True)
    assert hashlib.sha256(tool.read_bytes()).hexdigest() == TOOL_SHA256
    case = next(row for row in CASES["cases"] if row["id"] == case_id)
    request = _live_request(tmp_path, case, tool)
    result = collect_request(request, workspace=tmp_path, store=tmp_path / "store")
    validate("workflow_result", result)
    assert result["exit_code"] == (0 if case["expected_occurrences"] else 3)
    selected = result["final_run"]
    snapshot = RunStore.open_existing(tmp_path / "store").open_run(
        selected["run_id"], manifest_sha256=selected["manifest_sha256"]
    )
    snapshot.verify()
    receipts = {row["id"]: row for row in documents(snapshot, "execution_receipt")}
    assert all(
        receipts[name]["status"] == "passed"
        for name in ["tidy-version", "tidy", "build"]
    )
    assert any(
        b"19.1.7" in snapshot.read_bytes(identifier)
        for identifier in receipts["tidy-version"]["log_artifact_ids"]
    )
    facts = documents(snapshot, "external_analysis_facts")
    assert len(facts) == 1
    fact = facts[0]
    assert fact["origin"] == "import" and fact["scope_completeness"] == "unverified"
    assert fact["producer"] == PRODUCER
    assert fact["context_id"] == "tidy-context" and fact["scope_files"] == [
        "source.cpp"
    ]
    assert fact["receipt_id"] is None and fact["producer_version_receipt_id"] is None
    assert fact["proof_receipt_ids"] == []
    assert len(fact["observations"]) == case["expected_occurrences"]
    assert all(row["original_rule_id"] == case["check"] for row in fact["observations"])
    if case["expected_occurrences"]:
        assert all(
            (row["file"], row["line"], row["column"])
            == ("source.cpp", *LOCATIONS[case_id])
            for row in fact["observations"]
        )
    view = build_snapshot_view(snapshot)
    validate("snapshot_view", view)
    assert view.get("assessment") is None
    assert all(
        group["independent_confirmation"] is False
        and group["confidence_adjustment"] == 0
        for group in view.get("external_relationships", [])
    )
    html = render_snapshot_html(view)
    if case["expected_occurrences"]:
        assert case["check"] in html and fact["usability"] == "usable"
    else:
        assert fact["usability"] == "missing"
