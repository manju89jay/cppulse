"""Finding workflow contracts describe synthetic identities, never execution."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from cppulse.contracts import validate, validate_bundle
from cppulse.contracts.finding_workflows import anchor_fingerprint, scope_identity
from cppulse.errors import ContractError
from test_contracts_v2 import manifest_document


def baseline_document() -> dict[str, Any]:
    """Return a synthetic, self-consistent anchored baseline."""
    manifest = manifest_document()
    scope = {
        "files": ["src/main.cpp"],
        "context_ids": ["native"],
        "rule_ids": ["CPP-MOD-001"],
    }
    scope["sha256"] = scope_identity(scope)
    item = {
        "file": "src/main.cpp",
        "context_id": "native",
        "parse_context_digest": "c" * 64,
        "producer": {"name": "cppulse.native-normalizer", "version": "1.0.0"},
        "rule_id": "CPP-MOD-001",
        "rule_version": "prototype-1",
        "severity": "warning",
        "message": "Synthetic cast",
        "column": 4,
        "anchor_sha256": "d" * 64,
        "anchor_status": "unique",
        "count": 1,
        "observation_ids": ["observation-one"],
    }
    item["fingerprint"] = anchor_fingerprint(item)
    return {
        "version": "2.0.0",
        "id": "finding-baseline",
        "producer": {"name": "cppulse.findings", "version": "1.0.0"},
        "source_digest": manifest["source"]["digest"],
        "original_run_id": manifest["run_id"],
        "original_manifest_sha256": "a" * 64,
        "original_manifest_artifact_id": "original-manifest",
        "observations_artifact_ids": ["original-observations"],
        "created_at": "2026-11-13T12:00:00Z",
        "reason": "Synthetic contract baseline",
        "fingerprint_version": "native-line-anchor-1",
        "scope": scope,
        "config_digest": manifest["config_digest"],
        "cells": [
            {
                "file": "src/main.cpp",
                "context_id": "native",
                "parse_context_digest": "c" * 64,
                "inventory_id": "native-inventory",
                "source_artifact_id": "source-cpp",
                "source_sha256": "a" * 64,
                "registry_sha256": "e" * 64,
                "config_sha256": "f" * 64,
                "native_executable_sha256": "b" * 64,
                "status": "complete",
                "executed_rules": ["CPP-MOD-001"],
            }
        ],
        "findings": [item],
        "limitations": ["Synthetic identities; no execution claimed."],
    }


def suppression_record() -> dict[str, Any]:
    item = baseline_document()["findings"][0]
    return {
        "id": "reviewed-one",
        "gate": "finding_regression",
        "baseline_sha256": "a" * 64,
        "fingerprint_version": "native-line-anchor-1",
        "fingerprint": item["fingerprint"],
        "file": item["file"],
        "context_id": item["context_id"],
        "parse_context_digest": item["parse_context_digest"],
        "rule_id": item["rule_id"],
        "rule_version": item["rule_version"],
        "max_count": 1,
        "reason": "Synthetic reviewed scope",
        "owner": "fixture-owner",
        "approved_at": "2026-11-13T11:00:00Z",
        "expires_at": "2026-11-14T12:00:00Z",
    }


def comparison_document() -> dict[str, Any]:
    baseline = baseline_document()
    item = baseline["findings"][0]
    return {
        "version": "2.0.0",
        "id": "finding-comparison",
        "producer": {"name": "cppulse.findings", "version": "1.0.0"},
        "source_digest": baseline["source_digest"],
        "current_manifest_sha256": "b" * 64,
        "current_manifest_artifact_id": "current-manifest",
        "baseline_artifact_id": "raw-baseline",
        "baseline_sha256": "a" * 64,
        "baseline_manifest_artifact_id": "baseline-manifest",
        "baseline_manifest_sha256": "c" * 64,
        "fingerprint_version": "native-line-anchor-1",
        "generated_at": "2026-11-13T13:00:00Z",
        "scope": baseline["scope"],
        "rename_map": [],
        "max_new": 0,
        "gate": "passed",
        "comparable": True,
        "incomplete": False,
        "counts": {
            "current": 1,
            "baseline": 1,
            "new": 0,
            "unchanged": 1,
            "resolved": 0,
            "unknown_current": 0,
            "unknown_baseline": 0,
            "suppressed_new": 0,
            "unsuppressed_new": 0,
        },
        "groups": [
            {
                "file": item["file"],
                "context_id": item["context_id"],
                "rule_id": item["rule_id"],
                "fingerprint": item["fingerprint"],
                "baseline_fingerprint": item["fingerprint"],
                "current_observation_ids": ["current-one"],
                "baseline_observation_ids": ["observation-one"],
                "new_count": 0,
                "unchanged_count": 1,
                "resolved_count": 0,
                "unknown_current_count": 0,
                "unknown_baseline_count": 0,
                "suppressed_count": 0,
                "reason": "Synthetic equal multiplicity.",
            }
        ],
        "suppressions_artifact_id": None,
        "suppressions_sha256": None,
        "suppressions": [],
        "issues": [],
        "limitations": ["Synthetic comparison; raw source identities remain separate."],
    }


def test_new_finding_contracts_leave_historical_baseline_distinct() -> None:
    for kind, document in [
        ("finding_baseline", baseline_document()),
        ("finding_comparison", comparison_document()),
        (
            "finding_suppressions",
            {"version": "2.0.0", "records": [suppression_record()]},
        ),
    ]:
        validate(kind, document)


@pytest.mark.parametrize(
    "change",
    [
        "scope_hash",
        "unsafe_path",
        "missing_cell",
        "duplicate_cell",
        "missing_source",
        "unexecuted_rule",
        "duplicate_observation",
        "count",
        "fingerprint",
        "unknown_anchor",
        "unknown_version",
        "blank_reason",
    ],
)
def test_baseline_rejects_ambiguous_or_fabricated_internal_claims(change: str) -> None:
    document = baseline_document()
    if change == "scope_hash":
        document["scope"]["sha256"] = "0" * 64
    elif change == "unsafe_path":
        document["findings"][0]["file"] = "../escape.cpp"
    elif change == "missing_cell":
        document["cells"] = []
    elif change == "duplicate_cell":
        document["cells"].append(deepcopy(document["cells"][0]))
    elif change == "missing_source":
        document["cells"][0]["source_artifact_id"] = None
    elif change == "unexecuted_rule":
        document["cells"][0]["executed_rules"] = []
    elif change == "duplicate_observation":
        document["findings"][0]["observation_ids"] *= 2
    elif change == "count":
        document["findings"][0]["count"] = 2
    elif change == "fingerprint":
        document["findings"][0]["fingerprint"] = "0" * 64
    elif change == "unknown_anchor":
        document["findings"][0]["anchor_status"] = "unavailable"
    elif change == "unknown_version":
        document["fingerprint_version"] = "native-1"
    else:
        document["reason"] = " "
    with pytest.raises(ContractError):
        validate("finding_baseline", document)


def test_unavailable_anchor_has_no_invented_stable_hash() -> None:
    document = baseline_document()
    document["findings"][0].update(
        anchor_status="unavailable", anchor_sha256=None, fingerprint=None
    )
    validate("finding_baseline", document)


@pytest.mark.parametrize(
    "change",
    [
        "raw_total",
        "group_total",
        "false_pass",
        "hidden_unknown",
        "scope_unknown",
        "suppressed_without_request",
        "duplicate_current",
        "unknown_fingerprint",
        "missing_scope",
    ],
)
def test_comparison_conservation_and_gate_are_not_optional(change: str) -> None:
    document = comparison_document()
    if change == "raw_total":
        document["counts"]["current"] += 1
    elif change == "group_total":
        document["groups"][0]["new_count"] = 1
    elif change == "false_pass":
        document["counts"].update(baseline=0, unchanged=0, new=1, unsuppressed_new=1)
        document["groups"][0].update(
            baseline_observation_ids=[],
            baseline_fingerprint=None,
            unchanged_count=0,
            new_count=1,
        )
    elif change == "hidden_unknown":
        document["incomplete"] = True
    elif change == "scope_unknown":
        document["comparable"] = False
    elif change == "suppressed_without_request":
        document["counts"].update(baseline=0, unchanged=0, new=1, suppressed_new=1)
        document["groups"][0].update(
            baseline_observation_ids=[],
            baseline_fingerprint=None,
            unchanged_count=0,
            new_count=1,
            suppressed_count=1,
        )
    elif change == "duplicate_current":
        document["groups"].append(deepcopy(document["groups"][0]))
    elif change == "unknown_fingerprint":
        document["groups"][0]["fingerprint"] = None
    else:
        document["scope"]["files"] = []
        document["scope"]["sha256"] = scope_identity(document["scope"])
    with pytest.raises(ContractError):
        validate("finding_comparison", document)


def test_known_new_failure_can_be_incomplete_without_hiding_raw_count() -> None:
    document = comparison_document()
    document.update(gate="failed", incomplete=True)
    document["counts"].update(baseline=0, unchanged=0, new=1, unsuppressed_new=1)
    document["groups"][0].update(
        baseline_observation_ids=[],
        baseline_fingerprint=None,
        unchanged_count=0,
        new_count=1,
    )
    validate("finding_comparison", document)


@pytest.mark.parametrize(
    "change",
    [
        "wrong_gate",
        "expired_order",
        "blank_owner",
        "blank_reason",
        "duplicate_id",
        "overlap",
        "unsafe_path",
        "zero_count",
        "claimed_active",
    ],
)
def test_suppression_requests_are_exact_finite_and_expiring(change: str) -> None:
    record = suppression_record()
    document = {"version": "2.0.0", "records": [record]}
    if change == "wrong_gate":
        record["gate"] = "required_controls"
    elif change == "expired_order":
        record["expires_at"] = record["approved_at"]
    elif change == "blank_owner":
        record["owner"] = " "
    elif change == "blank_reason":
        record["reason"] = " "
    elif change == "duplicate_id":
        document["records"].append(deepcopy(record))
    elif change == "overlap":
        document["records"].append({**record, "id": "other"})
    elif change == "unsafe_path":
        record["file"] = "../escape.cpp"
    elif change == "zero_count":
        record["max_count"] = 0
    else:
        record["active"] = True
    with pytest.raises(ContractError):
        validate("finding_suppressions", document)


def check_request() -> dict[str, Any]:
    return {
        "version": "2.0.0",
        "baseline": {
            "source": "local_run",
            "store": "./old-output",
            "run_id": "baseline-run",
            "manifest_sha256": "a" * 64,
            "artifact_id": "baseline",
        },
        "scope_files": ["src/main.cpp"],
        "context_ids": ["native"],
        "rule_ids": ["CPP-MOD-001"],
        "max_new": 0,
    }


def test_check_requests_require_explicit_pinned_baseline_and_finite_scope() -> None:
    document = check_request()
    validate("finding_check_request", document)
    document["baseline"] = {
        "source": "transfer",
        "bundle": "./bundle",
        "root_id": "upstream",
        "manifest_sha256": "a" * 64,
        "artifact_id": "baseline",
    }
    document["rename_map"] = [{"from": "old.cpp", "to": "src/main.cpp"}]
    document["suppressions"] = {"source": "file", "path": "./suppressions.json"}
    validate("finding_check_request", document)
    validate(
        "finding_baseline_request",
        {
            "version": "2.0.0",
            "baseline_id": "baseline",
            "scope_files": ["src/main.cpp"],
            "context_ids": ["native"],
            "rule_ids": ["CPP-MOD-001"],
            "reason": "Explicit fixture baseline",
        },
    )


@pytest.mark.parametrize(
    "change",
    [
        "implicit_latest",
        "network",
        "empty_scope",
        "duplicate_scope",
        "rename_collision",
        "rename_traversal",
        "unsupported_option",
    ],
)
def test_finding_requests_reject_implicit_or_ambiguous_choices(change: str) -> None:
    document = check_request()
    if change == "implicit_latest":
        del document["baseline"]["manifest_sha256"]
    elif change == "network":
        document["baseline"]["store"] = "https://example.invalid/store"
    elif change == "empty_scope":
        document["scope_files"] = []
    elif change == "duplicate_scope":
        document["scope_files"] *= 2
    elif change == "rename_collision":
        document["rename_map"] = [
            {"from": "a.cpp", "to": "src/main.cpp"},
            {"from": "b.cpp", "to": "src/main.cpp"},
        ]
    elif change == "rename_traversal":
        document["rename_map"] = [{"from": "../a.cpp", "to": "src/main.cpp"}]
    else:
        document["changed_only"] = True
    with pytest.raises(ContractError):
        validate("finding_check_request", document)


def test_baseline_claims_need_retained_original_manifest_role_in_bundle() -> None:
    baseline = baseline_document()
    with pytest.raises(ContractError):
        validate_bundle(
            {"run_manifest": manifest_document(), "finding_baseline": baseline}
        )


def baseline_bundle() -> dict[str, Any]:
    """Bind a synthetic baseline to the already gated typed analysis fixture."""
    from test_analysis_inventory_contract import analysis_bundle

    data = analysis_bundle.__wrapped__()
    manifest = data["run_manifest"]
    inventory, execution = data["analysis_inventory"], data["execution_facts"]
    original = data["observations"]["items"][0]
    parse = next(
        row for row in manifest["contexts"] if row["id"] == original["context_id"]
    )
    descriptors = {row["id"]: row for row in manifest["artifacts"]}
    baseline = baseline_document()
    baseline.update(
        source_digest=manifest["source"]["digest"],
        config_digest=manifest["config_digest"],
    )
    cell = baseline["cells"][0]
    cell.update(
        inventory_id=inventory["id"],
        parse_context_digest=parse["digest"],
        registry_sha256=inventory["registry_sha256"],
        config_sha256=descriptors[inventory["config_artifact_id"]]["sha256"],
        native_executable_sha256=execution["executable_fact"]["sha256"],
    )
    item = baseline["findings"][0]
    for key in ["producer", "file", "rule_id", "rule_version", "severity", "message"]:
        item[key] = deepcopy(original[key])
    item.update(
        column=original.get("column"),
        parse_context_digest=parse["digest"],
        observation_ids=[original["id"]],
    )
    item["fingerprint"] = anchor_fingerprint(item)
    for identifier, sha, contract in [
        ("original-manifest", "a" * 64, None),
        (
            "original-observations",
            "4" * 64,
            {"kind": "observations", "version": "2.0.0"},
        ),
    ]:
        entry = {
            "id": identifier,
            "path": "finding-inputs/" + identifier + ".json",
            "sha256": sha,
            "size_bytes": 10,
            "media_type": "application/json",
        }
        if contract is not None:
            entry["contract"] = contract
        manifest["artifacts"].append(entry)
    data["finding_baseline"] = baseline
    return data


def comparison_bundle() -> dict[str, Any]:
    data = baseline_bundle()
    baseline = data.pop("finding_baseline")
    result = comparison_document()
    result.update(
        source_digest=data["run_manifest"]["source"]["digest"], scope=baseline["scope"]
    )
    item = baseline["findings"][0]
    result["groups"][0].update(
        fingerprint=item["fingerprint"],
        baseline_fingerprint=item["fingerprint"],
        current_observation_ids=item["observation_ids"],
        baseline_observation_ids=["historical-one"],
    )
    for role, sha in [
        ("current-manifest", "b" * 64),
        ("baseline-manifest", "c" * 64),
        ("raw-baseline", "a" * 64),
    ]:
        data["run_manifest"]["artifacts"].append(
            {
                "id": role,
                "path": "finding-inputs/" + role + ".json",
                "sha256": sha,
                "size_bytes": 10,
                "media_type": "application/json",
            }
        )
    data["finding_comparison"] = result
    return data


def mark_new(data: dict[str, Any], *, suppressed: bool = False) -> None:
    result = data["finding_comparison"]
    result["counts"].update(
        baseline=0,
        unchanged=0,
        new=1,
        unsuppressed_new=int(not suppressed),
        suppressed_new=int(suppressed),
    )
    result["groups"][0].update(
        baseline_observation_ids=[],
        baseline_fingerprint=None,
        unchanged_count=0,
        new_count=1,
        suppressed_count=int(suppressed),
    )
    result["gate"] = "passed" if suppressed else "failed"


def active_suppression_bundle() -> dict[str, Any]:
    data = comparison_bundle()
    mark_new(data, suppressed=True)
    result = data["finding_comparison"]
    row = suppression_record()
    row.update(
        fingerprint=result["groups"][0]["fingerprint"],
        rule_version=data["observations"]["items"][0]["rule_version"],
        parse_context_digest=next(
            row for row in data["run_manifest"]["contexts"] if row["id"] == "parse-main"
        )["digest"],
        active=True,
        applied_count=1,
        inactive_reason=None,
    )
    result.update(
        suppressions=[row],
        suppressions_artifact_id="raw-suppressions",
        suppressions_sha256="d" * 64,
    )
    data["run_manifest"]["artifacts"].append(
        {
            "id": "raw-suppressions",
            "path": "finding-inputs/raw-suppressions.json",
            "sha256": "d" * 64,
            "size_bytes": 10,
            "media_type": "application/json",
        }
    )
    return data


def test_closed_baseline_comparison_and_scoped_suppression_bind_current_facts() -> None:
    for data in [baseline_bundle(), comparison_bundle(), active_suppression_bundle()]:
        original = deepcopy(data)
        validate_bundle(data)
        assert data == original


@pytest.mark.parametrize(
    "change",
    [
        "source_role",
        "tool",
        "config",
        "registry",
        "context",
        "hide_observation",
        "changed_message",
        "partial_as_complete",
    ],
)
def test_baseline_cannot_relabel_current_native_metadata(change: str) -> None:
    data = baseline_bundle()
    baseline = data["finding_baseline"]
    if change == "source_role":
        baseline["cells"][0]["source_artifact_id"] = "registry"
    elif change in {"tool", "config", "registry"}:
        baseline["cells"][0][
            {
                "tool": "native_executable_sha256",
                "config": "config_sha256",
                "registry": "registry_sha256",
            }[change]
        ] = (
            "0" * 64
        )
    elif change == "context":
        baseline["cells"][0]["parse_context_digest"] = "0" * 64
        baseline["findings"][0]["parse_context_digest"] = "0" * 64
    elif change == "hide_observation":
        baseline["findings"] = []
    elif change == "changed_message":
        baseline["findings"][0]["message"] = "different"
        baseline["findings"][0]["fingerprint"] = anchor_fingerprint(
            baseline["findings"][0]
        )
    else:
        data["analysis_inventory"]["items"][0].update(
            status="partial", error_count=1, executed_rules=[]
        )
    with pytest.raises(ContractError):
        validate_bundle(data)


@pytest.mark.parametrize(
    "change",
    ["hide_current", "forged_id", "fallback_pass", "unverified_pass", "wrong_raw_hash"],
)
def test_comparison_cannot_hide_or_promote_unusable_current_facts(change: str) -> None:
    data = comparison_bundle()
    result = data["finding_comparison"]
    if change == "hide_current":
        result["groups"] = []
        result["counts"] = dict.fromkeys(result["counts"], 0)
    elif change == "forged_id":
        result["groups"][0]["current_observation_ids"] = ["unknown-observation"]
    elif change == "fallback_pass":
        data["analysis_inventory"]["items"][0].update(
            context_source="fallback", context_match="unverified"
        )
        data["analysis_inventory"]["compilation_database_artifact_id"] = None
    elif change == "unverified_pass":
        data["run_manifest"]["input_verification"] = "unverified"
    else:
        result["baseline_sha256"] = "0" * 64
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_known_new_from_a_matched_partial_ast_can_fail_incompletely() -> None:
    data = comparison_bundle()
    mark_new(data)
    data["analysis_inventory"]["items"][0].update(
        status="partial", error_count=1, executed_rules=[]
    )
    data["finding_comparison"]["incomplete"] = True
    validate_bundle(data)


def test_fallback_ast_cannot_definitively_introduce_a_named_job_finding() -> None:
    data = comparison_bundle()
    mark_new(data)
    data["analysis_inventory"]["items"][0].update(
        context_source="fallback", context_match="unverified"
    )
    data["analysis_inventory"]["compilation_database_artifact_id"] = None
    data["finding_comparison"]["incomplete"] = True
    with pytest.raises(ContractError):
        validate_bundle(data)


@pytest.mark.parametrize("change", ["parse_context", "rule_version"])
def test_active_suppression_cannot_borrow_another_observed_scope(change: str) -> None:
    data = active_suppression_bundle()
    row = data["finding_comparison"]["suppressions"][0]
    row["parse_context_digest" if change == "parse_context" else "rule_version"] = (
        "0" * 64 if change == "parse_context" else "future"
    )
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_anchor_identity_excludes_line_number_and_separate_job_context() -> None:
    item = baseline_document()["findings"][0]
    changed = {
        **item,
        "line": 999,
        "context_id": "another-job",
        "parse_context_digest": "0" * 64,
    }
    assert anchor_fingerprint(changed) == item["fingerprint"]
    assert anchor_fingerprint({**item, "file": "other/main.cpp"}) != item["fingerprint"]
    assert (
        anchor_fingerprint({**item, "anchor_sha256": "0" * 64}) != item["fingerprint"]
    )


def test_integral_json_coordinate_rendering_does_not_change_anchor_identity() -> None:
    item = baseline_document()["findings"][0]
    assert (
        anchor_fingerprint({**item, "column": float(item["column"])})
        == item["fingerprint"]
    )


def test_equal_fingerprints_keep_distinct_job_multiplicities() -> None:
    document = baseline_document()
    document["scope"]["context_ids"].append("second")
    document["scope"]["sha256"] = scope_identity(document["scope"])
    document["cells"].append({**document["cells"][0], "context_id": "second"})
    document["findings"].append(
        {
            **document["findings"][0],
            "context_id": "second",
            "observation_ids": ["second-observation"],
        }
    )
    validate("finding_baseline", document)
    assert sum(row["count"] for row in document["findings"]) == 2


@pytest.mark.parametrize("kind", ["finding_baseline", "finding_comparison"])
def test_workflow_timestamp_cannot_precede_used_current_analysis(kind: str) -> None:
    data = baseline_bundle() if kind == "finding_baseline" else comparison_bundle()
    for receipt in [
        next(row for row in data["execution_receipt"] if row["id"] == "analyze"),
        data["execution_facts"]["receipt"],
    ]:
        receipt.update(
            started_at="2026-11-13T14:00:00Z", finished_at="2026-11-13T14:00:00Z"
        )
    with pytest.raises(ContractError, match="predates"):
        validate_bundle(data)


@pytest.mark.parametrize(
    "rename",
    [
        [{"from": "unrelated-old.cpp", "to": "unrelated-new.cpp"}],
        [{"from": "src/main.cpp", "to": "src/main.cpp"}],
    ],
)
def test_unrelated_or_identity_rename_cannot_reclassify_a_different_fingerprint(rename):
    data = comparison_bundle()
    data["finding_comparison"]["groups"][0]["baseline_fingerprint"] = "0" * 64
    data["finding_comparison"]["rename_map"] = rename
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_fallback_context_keeps_occurrences_unknown_instead_of_known_unchanged():
    data = comparison_bundle()
    data["analysis_inventory"]["items"][0].update(
        context_source="fallback", context_match="unverified"
    )
    data["analysis_inventory"]["compilation_database_artifact_id"] = None
    result = data["finding_comparison"]
    result.update(gate="insufficient_evidence", incomplete=True, comparable=False)
    with pytest.raises(ContractError):
        validate_bundle(data)
    result["counts"].update(unchanged=0, unknown_current=1, unknown_baseline=1)
    result["groups"][0].update(
        unchanged_count=0, unknown_current_count=1, unknown_baseline_count=1
    )
    validate_bundle(data)
