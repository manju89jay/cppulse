"""Independent actual builtin-SDK qualification and retained-byte controls."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

import pytest

from cppulse.contracts import validate_bundle
from cppulse.errors import ContractError
from cppulse.pipeline import analyze
from cppulse.run_store import RunStore
from cppulse.workflows import read_documents
import test_bounded_pipeline as fixtures


@pytest.fixture(scope="module", params=["__stddef_size_t.h", "stddef.h"])
def sdk_run(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[Any, str]:
    root = tmp_path_factory.mktemp("actual-sdk-review")
    config = fixtures.config(root)
    (config.repo / "main.cpp").write_text(
        f"#include <{request.param}>\nint value() {{ return sizeof(size_t); }}\n"
    )
    (config.repo / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(config.repo),
                    "file": str(config.repo / "main.cpp"),
                    "arguments": [
                        "clang++",
                        "-std=c++17",
                        "-c",
                        str(config.repo / "main.cpp"),
                    ],
                }
            ]
        )
        + "\n"
    )
    with pytest.MonkeyPatch.context() as patch:
        fixtures.select_native(patch, fixtures.native.__wrapped__())
        summary = analyze(config, report_format="json", timeout=60)
    snapshot = RunStore(config.output).open_run(
        summary["run_id"], manifest_sha256=summary["manifest_sha256"]
    )
    return snapshot, request.param


def test_actual_sdk_bytes_are_bound_without_waiving_unsupported_queries(
    sdk_run: tuple[Any, str]
) -> None:
    snapshot, header = sdk_run
    documents = read_documents(snapshot)
    validate_bundle(documents)
    proof = documents["used_sdk_inputs"][0]
    available = [
        entry
        for unit in proof["units"]
        for entry in unit["entries"]
        if entry["status"] == "available"
    ]
    assert available
    for entry in available:
        content = snapshot.read_bytes(entry["artifact_id"])
        assert len(content) == entry["size_bytes"]
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    row = documents["analysis_inventory"][0]["items"][0]
    healths = documents["maintenance_health"]
    if header == "__stddef_size_t.h":
        health = next(
            row for row in healths if not row["scorer"]["allow_inferred_parse"]
        )
        assert row["buffer_coherence"] == "verified"
        assert health["aggregate"]["overall"] == 100
    else:
        health = healths[-1]
        # Actual Clang19 stddef.h contains inactive __has_include_next. The
        # finite conservative recognizer must not waive it merely for a score.
        assert row["buffer_coherence"] == "unverified"
        assert health["aggregate"]["overall"] is None


def test_changed_sdk_proof_link_cannot_keep_qualified_binding(
    sdk_run: tuple[Any, str]
) -> None:
    snapshot, _ = sdk_run
    documents = deepcopy(read_documents(snapshot))
    binding = documents["work_unit_analysis_binding"][0]
    assert binding.get("sdk_used_inputs_artifact_id")
    binding["sdk_used_inputs_artifact_id"] = "missing-sdk-proof"
    with pytest.raises(ContractError):
        validate_bundle(documents)


def test_omitted_sdk_proof_link_cannot_keep_qualified_binding(
    sdk_run: tuple[Any, str]
) -> None:
    snapshot, _ = sdk_run
    documents = deepcopy(read_documents(snapshot))
    binding = documents["work_unit_analysis_binding"][0]
    assert binding.pop("sdk_used_inputs_artifact_id", None)
    row = documents["analysis_inventory"][0]["items"][0]
    if row["buffer_coherence"] != "verified":
        assert all(
            health["aggregate"]["overall"] is None
            for health in documents.get("maintenance_health", [])
        )
        return
    with pytest.raises(ContractError):
        validate_bundle(documents)
