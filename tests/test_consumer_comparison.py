"""Configuration correspondence never substitutes for local application tests."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pytest

from cppulse.consumer import (
    compare_consumers,
    declare_consumer_matrix,
    describe_distribution,
    normalize_consumer_usage,
    persist_consumer_documents,
)
from cppulse.errors import ContractError
from cppulse.transfer import export_bundle
from test_consumer_usage import collect_actual_use


@pytest.fixture(scope="module")
def applicable(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    actual_use = collect_actual_use(tmp_path_factory.mktemp("consumer comparison"))
    roles = actual_use["roles"]
    usage = normalize_consumer_usage(
        actual_use["snapshot"],
        actual_use["subject"],
        usage_id="actual-package-use",
        receipt_id="consumer",
        configuration_probe_receipt_id="configuration",
        target_probe_receipt_id="target",
        required_artifact_ids=[roles["package/demo.hpp"], roles["package/libdemo.a"]],
        depfile_artifact_ids=[roles["build/main.d"]],
        link_map_artifact_id=roles["build/main.map"],
    )
    case = {
        "id": "selected-context",
        "required": True,
        "context_id": usage["context_id"],
        "configuration": deepcopy(usage["observed_configuration"]),
        "tests": ["required-application-workload"],
        "instantiations": [],
        "self_containment_headers": [],
        "usage_ids": [usage["id"]],
    }
    matrix = declare_consumer_matrix(
        actual_use["snapshot"],
        actual_use["subject"],
        matrix_id="selected-matrix",
        cases=[case],
    )
    local = persist_consumer_documents(
        actual_use["snapshot"],
        [
            ("distribution_subject", actual_use["subject"]),
            ("consumer_usage", usage),
            ("consumer_matrix", matrix),
        ],
        workspace=actual_use["workspace"],
        store=actual_use["snapshot"]._root,
    )
    upstream = export_bundle(
        {"upstream": local}, actual_use["workspace"] / "foreign-transfer"
    ).open_run("upstream")
    return {
        **actual_use,
        "local": local,
        "upstream": upstream,
        "matrix": matrix,
        "usage": usage,
    }


def compare(data: dict[str, Any], **selection: Any):
    return compare_consumers(
        data["upstream"],
        data["local"],
        upstream_subject_id=data["subject"]["id"],
        local_subject_id=data["subject"]["id"],
        upstream_matrix_id="selected-matrix",
        local_matrix_id=selection.pop("local_matrix_id", "selected-matrix"),
        generated_at=datetime.now(timezone.utc).isoformat(),
        **selection,
    )


def test_matching_observed_context_does_not_pass_missing_application_test(
    applicable: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_execution(*_: Any, **__: Any):
        raise AssertionError("Comparison must not execute a project")

    monkeypatch.setattr("subprocess.run", no_execution)
    result = compare(applicable)
    case = result.document["cases"][0]
    assert case["status"] == "compatible"
    assert case["local_test_status"] == "unknown"
    assert case["missing_local_checks"] == ["required-application-workload"]
    assert result.document["authentication"] == "unverified"
    assert result.document["import_origin"] == "import"
    assert (
        result.document["local_manifest_sha256"] == applicable["local"].manifest_sha256
    )
    assert len(result.artifacts) == 4


def test_comparison_retains_foreign_documents_as_raw_bytes_not_foreign_typed_source(
    applicable: dict[str, Any]
) -> None:
    result = compare(applicable)
    derived = persist_consumer_documents(
        applicable["local"],
        [("consumer_comparison", result.document)],
        workspace=applicable["workspace"],
        store=applicable["local"]._root,
        raw_artifacts=result.artifacts,
    )
    derived.verify()
    for artifact in result.artifacts:
        assert derived.read_bytes(artifact.id) == artifact.content
        assert "contract" not in next(
            row for row in derived.manifest["artifacts"] if row["id"] == artifact.id
        )
    assert derived.manifest["source"] == applicable["local"].manifest["source"]


def test_unknown_expected_dimension_cannot_receive_compatible_result(
    applicable: dict[str, Any]
) -> None:
    matrix = deepcopy(applicable["matrix"])
    matrix["id"] = "unknown-abi"
    matrix["cases"][0]["configuration"]["abi"] = None
    local = persist_consumer_documents(
        applicable["local"],
        [("consumer_matrix", matrix)],
        workspace=applicable["workspace"],
        store=applicable["local"]._root,
    )
    result = compare({**applicable, "local": local}, local_matrix_id=matrix["id"])
    assert result.document["cases"][0]["status"] == "unknown"


def test_unobserved_self_containment_remains_a_local_gap(
    applicable: dict[str, Any]
) -> None:
    matrix = deepcopy(applicable["matrix"])
    matrix["id"] = "header-check-required"
    matrix["cases"][0]["self_containment_headers"] = ["include/demo.hpp"]
    local = persist_consumer_documents(
        applicable["local"],
        [("consumer_matrix", matrix)],
        workspace=applicable["workspace"],
        store=applicable["local"]._root,
    )
    result = compare({**applicable, "local": local}, local_matrix_id=matrix["id"])
    assert "include/demo.hpp" in result.document["cases"][0]["missing_local_checks"]


def test_imported_run_cannot_be_used_as_current_local_evidence(
    applicable: dict[str, Any]
) -> None:
    with pytest.raises(ContractError, match="local"):
        compare({**applicable, "local": applicable["upstream"]})


def test_explicit_generation_time_cannot_precede_retained_facts(
    applicable: dict[str, Any]
) -> None:
    with pytest.raises(ContractError):
        compare_consumers(
            applicable["upstream"],
            applicable["local"],
            upstream_subject_id=applicable["subject"]["id"],
            local_subject_id=applicable["subject"]["id"],
            upstream_matrix_id="selected-matrix",
            local_matrix_id="selected-matrix",
            generated_at="2000-01-01T00:00:00Z",
        )


def test_unrelated_subject_cannot_borrow_a_verified_package_use(
    applicable: dict[str, Any], tmp_path
) -> None:
    snapshot = applicable["local"]
    probe = next(
        row
        for row in applicable["facts"]["configuration"]["binding"]["input_artifacts"]
        if row["path"] == "probe.cpp"
    )
    subject = describe_distribution(
        snapshot,
        subject_id="unused-subject",
        kind="header-only",
        distribution_files={"include/probe.hpp": probe["artifact_id"]},
    )
    matrix = deepcopy(applicable["matrix"])
    matrix.update(id="unused-subject-matrix", subject_id=subject["id"])
    local = persist_consumer_documents(
        snapshot,
        [("distribution_subject", subject), ("consumer_matrix", matrix)],
        workspace=applicable["workspace"],
        store=snapshot._root,
    )
    upstream = export_bundle(
        {"upstream": local}, tmp_path / "unused-transfer"
    ).open_run("upstream")
    result = compare_consumers(
        upstream,
        local,
        upstream_subject_id=subject["id"],
        local_subject_id=subject["id"],
        upstream_matrix_id=matrix["id"],
        local_matrix_id=matrix["id"],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    assert result.document["cases"][0]["status"] == "unknown"
    assert "subject" in result.document["cases"][0]["reason"]


@pytest.mark.parametrize("mutation", ["kind", "logical-path"])
def test_distribution_identity_mismatch_reports_incompatible_without_fake_compiler_mismatch(
    applicable: dict[str, Any], mutation: str
) -> None:
    original = applicable["subject"]
    files = {row["path"]: row["artifact_id"] for row in original["distribution_files"]}
    if mutation == "logical-path":
        files = {
            path.replace("libdemo.a", "renamed.a"): identifier
            for path, identifier in files.items()
        }
    subject = describe_distribution(
        applicable["local"],
        subject_id="changed-" + mutation,
        kind="header-only" if mutation == "kind" else "compiled",
        distribution_files=files,
    )
    roles = applicable["roles"]
    usage = normalize_consumer_usage(
        applicable["local"],
        subject,
        usage_id="use-" + mutation,
        receipt_id="consumer",
        configuration_probe_receipt_id="configuration",
        target_probe_receipt_id="target",
        required_artifact_ids=[roles["package/demo.hpp"], roles["package/libdemo.a"]],
        depfile_artifact_ids=[roles["build/main.d"]],
        link_map_artifact_id=roles["build/main.map"],
    )
    matrix = deepcopy(applicable["matrix"])
    matrix.update(id="matrix-" + mutation, subject_id=subject["id"])
    matrix["cases"][0]["usage_ids"] = [usage["id"]]
    local = persist_consumer_documents(
        applicable["local"],
        [
            ("distribution_subject", subject),
            ("consumer_usage", usage),
            ("consumer_matrix", matrix),
        ],
        workspace=applicable["workspace"],
        store=applicable["local"]._root,
    )
    result = compare_consumers(
        applicable["upstream"],
        local,
        upstream_subject_id=original["id"],
        local_subject_id=subject["id"],
        upstream_matrix_id="selected-matrix",
        local_matrix_id=matrix["id"],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    assert result.document["cases"][0]["status"] == "incompatible"
    assert result.document["cases"][0]["mismatches"] == ["distribution"]
