"""Semantic rendering of explicitly synthetic, hash-bound contract views."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from cppulse.contracts import validate
from cppulse.contracts.presentation import fact_summary
from cppulse.presentation import render_snapshot_html
from test_consumer_comparison_contract import comparison_bundle
from test_coverage_facts_contract import coverage_document
from test_sanitizer_facts_contract import sanitizer_bundle
from test_snapshot_view_contract import (
    descriptor,
    raw_json,
    rebind_manifest,
    snapshot_view,
)


def append_fact(view: dict[str, Any], kind: str, document: dict[str, Any]) -> None:
    """Add synthetic original bytes; this fixture never executes a tool."""
    identifier = "stored-" + kind
    text = raw_json(document)
    entry = descriptor(identifier, "facts/" + kind + ".json", text, kind)
    manifest = json.loads(view["run_manifest_json"])
    manifest["artifacts"].append(entry)
    view["artifacts"] = manifest["artifacts"]
    view["facts"].append(
        {
            "kind": kind,
            "artifact_id": identifier,
            "sha256": entry["sha256"],
            "size_bytes": entry["size_bytes"],
            "raw_json": text,
            **fact_summary(kind, document),
        }
    )
    rebind_manifest(view, manifest)
    validate("snapshot_view", view)


def test_typed_observations_render_without_legacy_and_preserve_two_context_occurrences() -> (
    None
):
    view = snapshot_view()
    manifest = json.loads(view["run_manifest_json"])
    other = deepcopy(manifest["contexts"][0])
    other["id"] = "gcc-other"
    manifest["contexts"].append(other)
    view["contexts"] = manifest["contexts"]
    rebind_manifest(view, manifest)
    observations = {
        "version": "2.0.0",
        "source_digest": view["source"]["digest"],
        "items": [],
    }
    for index, context in enumerate(["gcc17", "gcc-other"]):
        observations["items"].append(
            {
                "id": "observation-" + str(index),
                "producer": {"name": "synthetic-render-fixture", "version": "1"},
                "rule_id": "CPP-MEM-001",
                "rule_version": "prototype-1",
                "file": "src/main.cpp",
                "context_id": context,
                "line": 1,
                "column": 1,
                "severity": "warning",
                "message": "Visible repeated typed finding",
                "fingerprint": "b" * 64,
                "fingerprint_version": "synthetic-transport-1",
                "evidence_ids": [],
            }
        )
    append_fact(view, "observations", observations)
    html = render_snapshot_html(view)
    assert html.count("Visible repeated typed finding") == 2
    assert "CPP-MEM-001" in html and "src/main.cpp:1" in html
    assert "gcc17" in html and "gcc-other" in html


def test_coverage_kind_method_and_exact_counts_are_shown_without_percentage_math() -> (
    None
):
    view = snapshot_view()
    append_fact(view, "coverage_facts", coverage_document())
    html = render_snapshot_html(view)
    assert "lcov-da-v1" in html
    assert "1 / 2" in html


def test_sanitizer_outcome_and_original_diagnostic_are_visible_without_json_expansion() -> (
    None
):
    view = snapshot_view()
    document = sanitizer_bundle()["sanitizer_facts"]
    document["outcome"] = "failed"
    document["diagnostics"] = [
        {
            "id": "synthetic-diagnostic",
            "kind": "heap-buffer-overflow",
            "message": "Recorded synthetic sanitizer diagnostic.",
            "file": "src/main.cpp",
            "line": 1,
            "artifact_id": document["diagnostic_artifact_ids"][0],
            "test_case_id": document["exercise_proofs"][0]["test_case_ids"][0],
        }
    ]
    append_fact(view, "sanitizer_facts", document)
    html = render_snapshot_html(view)
    assert "heap-buffer-overflow" in html
    assert "Recorded synthetic sanitizer diagnostic." in html
    assert "asan" in html


def test_imported_consumer_applicability_stays_separate_from_local_check_gaps() -> None:
    view = snapshot_view()
    document = comparison_bundle()["consumer_comparison"]
    case = document["cases"][0]
    case.update(
        status="incompatible",
        mismatches=["abi"],
        local_test_status="unknown",
        required_local_checks=["local-link"],
        missing_local_checks=["local-link"],
    )
    case["matching_dimensions"].remove("abi")
    append_fact(view, "consumer_comparison", document)
    html = render_snapshot_html(view)
    assert "incompatible" in html and "unknown" in html
    assert "Dimension mismatches: abi" in html and "local-link" in html
    assert "authentication: unverified" in html


def test_recorded_per_file_parse_failure_is_visible_without_inventing_analysis_pass() -> (
    None
):
    view = snapshot_view()
    document = {
        "version": "2.0.0",
        "id": "synthetic-analysis",
        "source_digest": view["source"]["digest"],
        "producer": {"name": "synthetic-render-fixture", "version": "1"},
        "receipt_id": "unattempted",
        "job_context_id": "gcc17",
        "report_artifact_id": "synthetic-report",
        "registry_artifact_id": "synthetic-registry",
        "config_artifact_id": "synthetic-config",
        "compilation_database_artifact_id": None,
        "registry_sha256": "b" * 64,
        "requested_files": ["src/main.cpp"],
        "requested_rules": ["CPP-MEM-001"],
        "enabled_rules": ["CPP-MEM-001"],
        "items": [
            {
                "file": "src/main.cpp",
                "parse_context_id": None,
                "status": "failed",
                "error_count": 1,
                "context_source": "none",
                "context_match": "unverified",
                "executed_rules": [],
                "finding_count": 0,
                "limitations": ["Synthetic unavailable parse; no command executed."],
            }
        ],
        "limitations": ["Synthetic transport facts only."],
    }
    append_fact(view, "analysis_inventory", document)
    html = render_snapshot_html(view)
    assert "Recorded per-file analysis" in html
    assert "gcc17" in html and "src/main.cpp" in html
    assert "Synthetic unavailable parse" in html
