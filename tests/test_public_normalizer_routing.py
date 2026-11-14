"""Public role routing consumes freshly verified actual native-tool fixtures."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Any

import pytest

import cppulse.workflows as workflows
from cppulse.contracts import validate
from cppulse.run_store import RunStore
from test_collection import documents
from test_public_workflows import frozen_request

ROOT = Path(__file__).resolve().parents[1]


def by_artifact(
    snapshot: Any, step: str, direction: str, identifier: str
) -> dict[str, Any]:
    """Translate an existing observed ID to the public declared path selector."""
    fact = next(
        row
        for row in documents(snapshot, "execution_facts")
        if row["receipt"]["id"] == step
    )
    path = next(
        row["path"]
        for row in fact["binding"][direction + "_artifacts"]
        if row["artifact_id"] == identifier
    )
    return {"step_id": step, "role": direction, "path": path}


def test_public_coverage_routing_keeps_distinct_actual_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.demo_coverage import prepare_collection, roles, selected_tool

    gcovr = os.environ.get(
        "CPPULSE_GCOVR", str(ROOT.parent / "tooling/gcovr-8.8/bin/gcovr")
    )
    requested = {
        "compiler": "g++-14",
        "gcov": "gcov-14",
        "gcovr": gcovr,
        "cmake": "cmake",
        "ctest": "ctest",
    }
    if any(shutil.which(value) is None for value in requested.values()):
        pytest.skip("Optional pinned coverage verification toolchain unavailable")
    raw, workspace = prepare_collection(
        tmp_path / "actual",
        **{key: selected_tool(value) for key, value in requested.items()},
    )
    request = frozen_request(raw)
    for adapter in ["lcov", "cobertura"]:
        selected = roles(raw, adapter)
        item = {
            "id": "public-" + adapter,
            "kind": "coverage",
            "normalizer_version": "1.0.0",
            "step_id": selected["receipt_id"],
            "adapter": adapter,
            "report": by_artifact(
                raw, selected["receipt_id"], "output", selected["report_artifact_id"]
            ),
            "producer_version_step_id": selected["producer_version_receipt_id"],
            "gcov_version_step_id": selected["gcov_version_receipt_id"],
            "compiler_version_step_id": selected["compiler_version_receipt_id"],
            "configuration": by_artifact(
                raw,
                selected["receipt_id"],
                "input",
                selected["configuration_artifact_id"],
            ),
            "gcov": by_artifact(
                raw, selected["receipt_id"], "input", selected["gcov_artifact_id"]
            ),
            "proof_step_ids": selected["proof_receipt_ids"],
            "test_binding_ids": selected["test_evidence_ids"],
            "instrumentation": [
                {
                    "object": by_artifact(
                        raw, "compile", "output", row["object_artifact_id"]
                    ),
                    "mapping": by_artifact(
                        raw, "compile", "output", row["mapping_artifact_id"]
                    ),
                    "source_files": row["source_files"],
                }
                for row in selected["instrumentation"]
            ],
            "profiles": [
                {
                    "profile": by_artifact(
                        raw, row["test_receipt_id"], "output", row["artifact_id"]
                    ),
                    "binary": by_artifact(
                        raw, "link", "output", row["binary_artifact_id"]
                    ),
                    "test_step_id": row["test_receipt_id"],
                }
                for row in selected["profiles"]
            ],
        }
        request["normalizers"].append(item)
    validate("collection_request", request)
    monkeypatch.setattr(workflows, "collect", lambda *args, **kwargs: raw)
    result = workflows.collect_request(
        request, workspace=workspace, store=raw.path.parents[1]
    )
    assert result["status"] == "completed"
    assert len(result["normalizers"]) == 2 and all(
        row["usability"] == "usable" for row in result["normalizers"]
    )
    final = RunStore.open_existing(raw.path.parents[1]).open_run(
        result["final_run"]["run_id"]
    )
    facts = documents(final, "coverage_facts")
    assert len(facts) == 2
    assert {row["adapter"]["name"] for row in facts} == {"lcov", "cobertura"}
    assert all(row["files"][0]["measurements"][0]["covered"] == 5 for row in facts)


def test_public_sanitizer_routing_retains_actual_instrumentation_and_case_proofs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.demo_sanitizers import collect_case, selected_tools

    store = RunStore(tmp_path / "store")
    case = collect_case(
        tmp_path / "actual",
        "ubsan",
        "clean",
        selected_tools(),
        ROOT / "demo/sanitizer-fixture",
        store,
    )
    raw = store.open_run(
        case["raw_run_id"], manifest_sha256=case["raw_manifest_sha256"]
    )
    request = frozen_request(raw)
    request["normalizers"] = [
        {
            "id": "public-ubsan",
            "kind": "sanitizer",
            "normalizer_version": "1.0.0",
            "sanitizer": "ubsan",
            "requested_files": ["main.cpp"],
            "compiler_version_step_id": "compiler-version",
            "nm_version_step_id": "nm-version",
            "readelf_version_step_id": "readelf-version",
            "objects": [
                {
                    "compile_step_id": "compile",
                    "nm_step_id": "nm-object",
                    "elf_step_id": "elf-object",
                }
            ],
            "link_step_id": "link",
            "runtime_inspection_step_id": "elf-binary",
            "test_binding_id": "sanitizer-tests",
        }
    ]
    validate("collection_request", request)
    monkeypatch.setattr(workflows, "collect", lambda *args, **kwargs: raw)
    result = workflows.collect_request(
        request, workspace=Path(case["workspace"]), store=tmp_path / "store"
    )
    assert result["status"] == "completed"
    record = result["normalizers"][0]
    assert record["outcome"] == "passed" and record["usability"] == "usable"
    final = store.open_run(result["final_run"]["run_id"])
    fact = documents(final, "sanitizer_facts")[0]
    assert (
        fact["id"] == "public-ubsan"
        and fact["exercise_proofs"]
        and fact["object_proofs"]
    )
