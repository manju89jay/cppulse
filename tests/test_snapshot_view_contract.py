"""Pinned presentation contracts preserve stored facts without new gate arithmetic."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

import pytest

from cppulse.contracts import load_schema, validate
from cppulse.errors import ContractError
from test_contracts_v2 import assessment_document, manifest_document


def raw_json(document: dict[str, Any]) -> str:
    """Represent synthetic stored bytes; no tool execution claim is made."""
    return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def descriptor(identifier: str, path: str, raw: str, kind: str) -> dict[str, Any]:
    """Return exact byte metadata for one explicitly synthetic typed artifact."""
    data = raw.encode("utf-8")
    return {
        "id": identifier,
        "path": path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "media_type": "application/json",
        "contract": {"kind": kind, "version": "2.0.0"},
    }


def test_snapshot_view_is_a_packaged_distinct_contract() -> None:
    assert load_schema("snapshot_view")["title"]


def display(document: dict[str, Any]) -> dict[str, Any]:
    """Copy stored assessment values, converting selected numeric leaves only."""
    result = deepcopy(document)
    result["weights"] = {key: str(value) for key, value in document["weights"].items()}
    result["scores"] = {
        key: None if value is None else str(value)
        for key, value in document["scores"].items()
    }
    for control in result["controls"]:
        control["weight"] = str(control["weight"])
    return result


def snapshot_view(
    *, assessed: bool = True, status: str = "completed"
) -> dict[str, Any]:
    """Build one internally consistent synthetic stored view, not executed facts."""
    manifest = manifest_document()
    manifest["status"] = status
    manifest["input_verification"] = "verified"
    manifest["limitations"] = [
        "Synthetic contract fixture; no execution or authenticity claim."
    ]
    if status != "completed":
        manifest["stages"][0].update(
            status="cancelled" if status == "cancelled" else "error",
            reason="Synthetic incomplete stage",
        )
    assessment = assessment_document()
    for control in assessment["controls"]:
        control["context_ids"] = [manifest["contexts"][0]["id"]]
    assessment_raw = raw_json(assessment)
    assessment_descriptor = descriptor(
        "assessment-stored", "assessment/selected.json", assessment_raw, "assessment"
    )
    if assessed:
        manifest["artifacts"].append(assessment_descriptor)
    manifest_raw = raw_json(manifest)
    return {
        "version": "2.0.0",
        "run_manifest_json": manifest_raw,
        "run": {
            "id": manifest["run_id"],
            "manifest_sha256": hashlib.sha256(manifest_raw.encode()).hexdigest(),
            "status": manifest["status"],
            "input_verification": manifest["input_verification"],
            "source_digest": manifest["source"]["digest"],
            "inventory_complete": manifest["source"]["inventory_complete"],
            "started_at": manifest["started_at"],
            "finished_at": manifest["finished_at"],
            "config_digest": manifest["config_digest"],
            "limitations": manifest["limitations"],
        },
        "source": manifest["source"],
        "stages": manifest["stages"],
        "contexts": manifest["contexts"],
        "assessment": (
            {
                "artifact_id": assessment_descriptor["id"],
                "sha256": assessment_descriptor["sha256"],
                "size_bytes": assessment_descriptor["size_bytes"],
                "raw_json": assessment_raw,
                "display": display(assessment),
            }
            if assessed
            else None
        ),
        "facts": [],
        "artifacts": manifest["artifacts"],
        "legacy": {
            name: None for name in ["findings", "git_metrics", "risk_scores", "roadmap"]
        },
        "gaps": (
            []
            if assessed
            else [
                {
                    "kind": "assessment",
                    "id": None,
                    "message": "No stored assessment selected.",
                    "artifact_ids": [],
                }
            ]
        ),
        "limitations": list(manifest["limitations"]),
    }


def rebind_manifest(view: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Update raw manifest identity after a purposeful synthetic fixture change."""
    view["run_manifest_json"] = raw_json(manifest)
    view["run"]["manifest_sha256"] = hashlib.sha256(
        view["run_manifest_json"].encode()
    ).hexdigest()


def rebind_assessment(view: dict[str, Any], document: dict[str, Any]) -> None:
    """Bind changed stored assessment bytes without hiding summary mismatches."""
    raw = raw_json(document)
    entry = view["assessment"]
    entry.update(
        raw_json=raw,
        sha256=hashlib.sha256(raw.encode()).hexdigest(),
        size_bytes=len(raw.encode()),
    )
    manifest = json.loads(view["run_manifest_json"])
    artifact = next(
        row for row in manifest["artifacts"] if row["id"] == entry["artifact_id"]
    )
    artifact.update(sha256=entry["sha256"], size_bytes=entry["size_bytes"])
    view["artifacts"] = manifest["artifacts"]
    rebind_manifest(view, manifest)


@pytest.mark.parametrize("status", ["completed", "partial", "cancelled"])
@pytest.mark.parametrize("assessed", [True, False])
def test_assessed_unassessed_and_incomplete_runs_remain_distinct(
    status: str, assessed: bool
) -> None:
    view = snapshot_view(assessed=assessed, status=status)
    validate("snapshot_view", view)
    assert view["run"]["status"] == status
    assert (view["assessment"] is not None) == assessed


def test_exact_large_stored_weights_are_strings_without_precision_loss() -> None:
    view = snapshot_view()
    document = json.loads(view["assessment"]["raw_json"])
    huge = 10**400
    for control in document["controls"]:
        control["weight"] *= huge
    document["weights"] = {
        key: value * huge for key, value in document["weights"].items()
    }
    rebind_assessment(view, document)
    view["assessment"]["display"] = display(document)
    validate("snapshot_view", view)
    assert view["assessment"]["display"]["weights"]["passed"] == str(4 * huge)
    assert isinstance(view["assessment"]["display"]["scores"]["readiness"], str)


@pytest.mark.parametrize(
    "field",
    [
        "gate",
        "score",
        "weight",
        "control_status",
        "control_weight",
        "reason",
        "context",
        "policy",
        "deviations",
    ],
)
def test_display_never_replaces_any_stored_assessment_value(field: str) -> None:
    view = snapshot_view()
    shown = view["assessment"]["display"]
    if field == "gate":
        shown["gate"] = "passed"
    elif field == "score":
        shown["scores"]["readiness"] = "99"
    elif field == "weight":
        shown["weights"]["passed"] = "9007199254740993"
    elif field == "control_status":
        shown["controls"][0]["status"] = "unknown"
    elif field == "control_weight":
        shown["controls"][0]["weight"] = "4.1"
    elif field == "reason":
        shown["controls"][0]["reason"] = "Invented result"
    elif field == "context":
        shown["controls"][0]["context_ids"] = ["other-job"]
    elif field == "policy":
        shown["policy"]["sha256"] = "f" * 64
    else:
        shown["deviations"] = [{"invented": True}]
    with pytest.raises(ContractError):
        validate("snapshot_view", view)


@pytest.mark.parametrize(
    "field",
    [
        "pin",
        "run_id",
        "source",
        "source_digest",
        "inventory",
        "status",
        "stages",
        "contexts",
        "artifacts",
        "configuration",
    ],
)
def test_all_run_summaries_are_bound_to_exact_original_manifest_bytes(
    field: str,
) -> None:
    view = snapshot_view()
    if field == "pin":
        view["run"]["manifest_sha256"] = "b" * 64
    elif field == "run_id":
        view["run"]["id"] = "different-run"
    elif field == "source":
        view["source"] = deepcopy(view["source"])
        view["source"]["limitations"] = ["Different selected source"]
    elif field == "source_digest":
        view["run"]["source_digest"] = "b" * 64
    elif field == "inventory":
        view["run"]["inventory_complete"] = False
    elif field == "status":
        view["run"]["status"] = "partial"
    elif field == "stages":
        view["stages"] = []
    elif field == "contexts":
        view["contexts"] = []
    elif field == "artifacts":
        view["artifacts"] = []
    else:
        view["run"]["config_digest"] = "b" * 64
    with pytest.raises(ContractError):
        validate("snapshot_view", view)


@pytest.mark.parametrize(
    "field", ["artifact_id", "sha256", "size_bytes", "raw_json", "contract_kind"]
)
def test_selected_assessment_must_resolve_exact_original_descriptor(field: str) -> None:
    view = snapshot_view()
    if field == "artifact_id":
        view["assessment"][field] = "not-selected"
    elif field == "sha256":
        view["assessment"][field] = "b" * 64
    elif field == "size_bytes":
        view["assessment"][field] += 1
    elif field == "raw_json":
        view["assessment"][field] += " "
    else:
        manifest = json.loads(view["run_manifest_json"])
        manifest["artifacts"][-1]["contract"]["kind"] = "policy"
        view["artifacts"] = manifest["artifacts"]
        rebind_manifest(view, manifest)
    with pytest.raises(ContractError):
        validate("snapshot_view", view)


def test_assessment_cannot_belong_to_another_source_or_unknown_job() -> None:
    for field in ["source", "context"]:
        view = snapshot_view()
        document = json.loads(view["assessment"]["raw_json"])
        if field == "source":
            document["source_digest"] = "b" * 64
        else:
            document["controls"][0]["context_ids"] = ["unlisted-job"]
        rebind_assessment(view, document)
        view["assessment"]["display"] = display(document)
        with pytest.raises(ContractError):
            validate("snapshot_view", view)


def add_receipt(view: dict[str, Any]) -> None:
    """Retain one typed receipt as raw bytes and its exact safe display summary."""
    from test_contracts_v2 import receipt_document

    document = receipt_document()
    raw = raw_json(document)
    artifact = descriptor(
        "receipt-document", "receipts/tests.json", raw, "execution_receipt"
    )
    view["facts"].append(
        {
            "kind": "execution_receipt",
            "artifact_id": artifact["id"],
            "sha256": artifact["sha256"],
            "size_bytes": artifact["size_bytes"],
            "raw_json": raw,
            "id": document["id"],
            "context_ids": [document["context_id"]],
            "origin": None,
            "producer": document["producer"],
            "status": document["status"],
            "usability": None,
            "limitations": [],
        }
    )
    manifest = json.loads(view["run_manifest_json"])
    manifest["artifacts"].append(artifact)
    view["artifacts"] = manifest["artifacts"]
    rebind_manifest(view, manifest)


def test_typed_fact_summaries_keep_raw_64_bit_process_facts_without_js_numbers() -> (
    None
):
    view = snapshot_view()
    add_receipt(view)
    validate("snapshot_view", view)
    assert isinstance(view["facts"][0]["raw_json"], str)
    assert "document" not in view["facts"][0]


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "context_ids",
        "status",
        "producer",
        "origin",
        "usability",
        "limitations",
        "sha256",
        "size_bytes",
        "kind",
        "artifact_id",
    ],
)
def test_typed_fact_summaries_and_bytes_cannot_contradict_stored_document(
    field: str,
) -> None:
    view = snapshot_view()
    add_receipt(view)
    row = view["facts"][0]
    if field in {"id", "artifact_id"}:
        row[field] = "different"
    elif field == "context_ids":
        row[field] = ["other-job"]
    elif field == "status":
        row[field] = "failed"
    elif field == "producer":
        row[field] = {"name": "invented", "version": "1"}
    elif field == "origin":
        row[field] = "execution"
    elif field == "usability":
        row[field] = "usable"
    elif field == "limitations":
        row[field] = ["Invented qualification"]
    elif field == "sha256":
        row[field] = "b" * 64
    elif field == "size_bytes":
        row[field] += 1
    else:
        row[field] = "policy"
    with pytest.raises(ContractError):
        validate("snapshot_view", view)


def test_duplicate_artifact_or_fact_rows_are_not_hidden_by_display_dictionaries() -> (
    None
):
    for section in ["artifacts", "facts"]:
        view = snapshot_view()
        add_receipt(view)
        view[section].append(deepcopy(view[section][-1]))
        with pytest.raises(ContractError):
            validate("snapshot_view", view)


def add_legacy(view: dict[str, Any]) -> None:
    """Bind a clearly synthetic empty findings document from this one snapshot."""
    document = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/synthetic",
            "analyzed_at": "2026-11-13T10:00:00Z",
            "file_count": 0,
            "total_loc": 0,
        },
        "findings": [],
        "summary": {"total_findings": 0, "by_category": {}, "by_severity": {}},
    }
    raw = raw_json(document)
    artifact = descriptor("legacy-findings", "prototype/findings.json", raw, "findings")
    artifact["contract"]["version"] = "prototype_v1"
    view["legacy"]["findings"] = {
        "artifact_id": artifact["id"],
        "sha256": artifact["sha256"],
        "size_bytes": artifact["size_bytes"],
        "raw_json": raw,
        "document": document,
    }
    manifest = json.loads(view["run_manifest_json"])
    manifest["artifacts"].append(artifact)
    view["artifacts"] = manifest["artifacts"]
    rebind_manifest(view, manifest)


def test_legacy_slots_retain_validated_bytes_and_explicit_missing_siblings() -> None:
    view = snapshot_view()
    add_legacy(view)
    validate("snapshot_view", view)
    assert view["legacy"]["git_metrics"] is None


@pytest.mark.parametrize(
    "field", ["document", "raw_json", "artifact_id", "sha256", "size_bytes", "kind"]
)
def test_legacy_cannot_read_a_flat_file_or_another_artifact_as_snapshot_output(
    field: str,
) -> None:
    view = snapshot_view()
    add_legacy(view)
    slot = view["legacy"]["findings"]
    if field == "document":
        slot["document"]["metadata"]["repo_path"] = "/different"
    elif field == "raw_json":
        slot["raw_json"] += "\n"
    elif field == "artifact_id":
        slot[field] = "not-in-this-snapshot"
    elif field == "sha256":
        slot[field] = "b" * 64
    elif field == "size_bytes":
        slot[field] += 1
    else:
        manifest = json.loads(view["run_manifest_json"])
        manifest["artifacts"][-1]["contract"]["kind"] = "roadmap"
        view["artifacts"] = manifest["artifacts"]
        rebind_manifest(view, manifest)
    with pytest.raises(ContractError):
        validate("snapshot_view", view)


def test_raw_json_whitespace_and_unicode_are_hashed_as_actual_bytes() -> None:
    view = snapshot_view()
    manifest = json.loads(view["run_manifest_json"])
    manifest["limitations"].append("Retained source note: λ")
    view["run"]["limitations"] = manifest["limitations"]
    view["limitations"] = manifest["limitations"]
    # Deliberately noncanonical whitespace; pin validation must not reserialize.
    raw = json.dumps(manifest, ensure_ascii=False, indent=1) + " \n"
    view["run_manifest_json"] = raw
    view["run"]["manifest_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    validate("snapshot_view", view)


@pytest.mark.parametrize("which", ["manifest", "assessment", "fact", "legacy"])
def test_malformed_embedded_raw_json_is_a_contract_error(which: str) -> None:
    view = snapshot_view()
    if which == "manifest":
        view["run_manifest_json"] = "{"
    elif which == "assessment":
        view["assessment"]["raw_json"] = "{"
    elif which == "fact":
        add_receipt(view)
        view["facts"][0]["raw_json"] = "{"
    else:
        add_legacy(view)
        view["legacy"]["findings"]["raw_json"] = "{"
    with pytest.raises(ContractError):
        validate("snapshot_view", view)


def test_no_new_policy_gate_is_computed_for_a_presentation_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cppulse.contracts.validation as validation

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("A presentation view must not evaluate a policy gate")

    monkeypatch.setattr(validation, "policy_gate", forbidden)
    validate("snapshot_view", snapshot_view())


def test_shared_projections_preserve_sanitizer_and_process_status_distinctions() -> (
    None
):
    from cppulse.contracts.presentation import assessment_display, fact_summary

    raw = assessment_document()
    shown = assessment_display(raw)
    assert shown == display(raw)
    shown["controls"][0]["reason"] = "changed caller copy"
    assert raw["controls"][0]["reason"] != shown["controls"][0]["reason"]
    assert (
        fact_summary(
            "sanitizer_facts", {"outcome": "unsupported", "usability": "unsupported"}
        )["status"]
        == "unsupported"
    )
    process = fact_summary(
        "execution_facts",
        {
            "receipt": {"id": "command", "status": "passed", "context_id": "job"},
            "material_status": "missing",
        },
    )
    assert process["status"] == "passed"
    assert process["context_ids"] == ["job"]


def test_embedded_json_bounds_and_duplicate_keys_fail_as_contract_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cppulse.contracts.presentation as module

    view = snapshot_view()
    original = view["run_manifest_json"]
    for value in [
        "[" * 129 + "]" * 129,
        '{"run_id":"first","run_id":"second"}',
        '{"value":NaN}',
        '{"value":Infinity}',
        "[]",
        "\ud800",
    ]:
        view["run_manifest_json"] = value
        with pytest.raises(ContractError):
            validate("snapshot_view", view)
    view["run_manifest_json"] = original
    monkeypatch.setattr(module, "MAX_RAW_JSON_BYTES", 128)
    with pytest.raises(ContractError, match="bound"):
        validate("snapshot_view", view)


def test_missing_assessment_gap_and_unknown_gap_artifacts_are_rejected() -> None:
    view = snapshot_view(assessed=False)
    view["gaps"] = []
    with pytest.raises(ContractError):
        validate("snapshot_view", view)
    view = snapshot_view(assessed=False)
    view["gaps"][0]["artifact_ids"] = ["foreign-output"]
    with pytest.raises(ContractError):
        validate("snapshot_view", view)


def test_missing_input_verification_remains_unverified() -> None:
    view = snapshot_view()
    manifest = json.loads(view["run_manifest_json"])
    del manifest["input_verification"]
    view["run"]["input_verification"] = "unverified"
    rebind_manifest(view, manifest)
    validate("snapshot_view", view)
    view["run"]["input_verification"] = "verified"
    with pytest.raises(ContractError):
        validate("snapshot_view", view)


def test_fresh_hashes_do_not_allow_a_fact_to_change_source_or_job_identity() -> None:
    for field in ["source_digest", "context_id"]:
        view = snapshot_view()
        add_receipt(view)
        fact = view["facts"][0]
        raw = json.loads(fact["raw_json"])
        raw[field] = "b" * 64 if field == "source_digest" else "other-job"
        text = raw_json(raw)
        fact.update(
            raw_json=text,
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            size_bytes=len(text.encode()),
        )
        if field == "context_id":
            fact["context_ids"] = [raw[field]]
        manifest = json.loads(view["run_manifest_json"])
        stored = next(
            row for row in manifest["artifacts"] if row["id"] == fact["artifact_id"]
        )
        stored.update(sha256=fact["sha256"], size_bytes=fact["size_bytes"])
        view["artifacts"] = manifest["artifacts"]
        rebind_manifest(view, manifest)
        with pytest.raises(ContractError):
            validate("snapshot_view", view)


def test_numeric_display_preserves_original_decimal_tokens_beyond_float_precision() -> (
    None
):
    view = snapshot_view()
    document = json.loads(view["assessment"]["raw_json"])
    huge = 9007199254740993
    control = document["controls"][0]
    control.update(status="passed", weight=huge, required=False)
    document["controls"] = [control]
    document.update(
        gate="passed",
        weights={"passed": huge, "failed": 0, "unknown": 0},
        scores={name: 100 for name in document["scores"]},
    )
    rebind_assessment(view, document)
    raw = view["assessment"]["raw_json"].replace(str(huge), str(huge) + ".0")
    manifest = json.loads(view["run_manifest_json"])
    entry = view["assessment"]
    entry.update(
        raw_json=raw,
        sha256=hashlib.sha256(raw.encode()).hexdigest(),
        size_bytes=len(raw.encode()),
    )
    for artifact in manifest["artifacts"]:
        if artifact["id"] == entry["artifact_id"]:
            artifact.update(sha256=entry["sha256"], size_bytes=entry["size_bytes"])
    view["artifacts"] = manifest["artifacts"]
    rebind_manifest(view, manifest)
    shown = display(document)
    shown["weights"]["passed"] = str(huge) + ".0"
    shown["controls"][0]["weight"] = str(huge) + ".0"
    entry["display"] = shown
    validate("snapshot_view", view)
    entry["display"]["weights"]["passed"] = str(float(str(huge) + ".0"))
    with pytest.raises(ContractError):
        validate("snapshot_view", view)


def test_selected_assessment_run_id_must_name_this_exact_pinned_snapshot() -> None:
    view = snapshot_view()
    document = json.loads(view["assessment"]["raw_json"])
    document["run_id"] = "different-ancestor"
    rebind_assessment(view, document)
    view["assessment"]["display"] = display(document)
    with pytest.raises(ContractError):
        validate("snapshot_view", view)


def test_missing_requested_job_is_visible_as_stored_unknown_not_rejected() -> None:
    view = snapshot_view()
    document = json.loads(view["assessment"]["raw_json"])
    missing = next(
        control for control in document["controls"] if control["status"] == "unknown"
    )
    missing.update(context_ids=["expected-not-collected"], incomplete=True)
    rebind_assessment(view, document)
    view["assessment"]["display"] = display(document)
    validate("snapshot_view", view)
    assert view["assessment"]["display"]["controls"][-1]["context_ids"] == [
        "expected-not-collected"
    ]


def test_not_applicable_control_may_preserve_an_uncollected_requested_context() -> None:
    view = snapshot_view()
    document = json.loads(view["assessment"]["raw_json"])
    control = document["controls"][0]
    control.update(
        status="not_applicable",
        reason="No eligible files in selected policy scope.",
        context_ids=["requested-not-applicable"],
    )
    document["controls"] = [control]
    document.update(
        gate="insufficient_evidence",
        weights={key: 0 for key in document["weights"]},
        scores={key: None for key in document["scores"]},
    )
    rebind_assessment(view, document)
    view["assessment"]["display"] = display(document)
    validate("snapshot_view", view)


@pytest.mark.parametrize("wrong_source", [False, True])
def test_embedded_execution_receipt_source_is_bound_even_when_material_is_missing(
    wrong_source: bool,
) -> None:
    from cppulse.contracts.presentation import fact_summary
    from test_contracts_v2 import receipt_document

    view = snapshot_view()
    receipt = receipt_document()
    if wrong_source:
        receipt["source_digest"] = "b" * 64
    document = {
        "version": "2.0.0",
        "collector_version": "1.0.0",
        "receipt": receipt,
        "input_facts": [],
        "input_after_facts": [],
        "output_facts": [],
        "preexisting_output_facts": [],
        "executable_fact": None,
        "material_status": "missing",
        "limitations": ["Synthetic missing material"],
        "stdout_bytes": 0,
        "stderr_bytes": 0,
        "captured_bytes": 0,
        "logs_truncated": False,
        "snapshot_limitations": [],
        "binding": {
            "status": "not_collected",
            "limitations": [],
            "input_artifacts": [],
            "output_artifacts": [],
            "log_artifacts": {"stdout": None, "stderr": None},
        },
    }
    raw = raw_json(document)
    artifact = descriptor(
        "execution-facts", "facts/execution.json", raw, "execution_facts"
    )
    view["facts"] = [
        {
            "kind": "execution_facts",
            "artifact_id": artifact["id"],
            "sha256": artifact["sha256"],
            "size_bytes": artifact["size_bytes"],
            "raw_json": raw,
            **fact_summary("execution_facts", document),
        }
    ]
    manifest = json.loads(view["run_manifest_json"])
    manifest["artifacts"].append(artifact)
    view["artifacts"] = manifest["artifacts"]
    rebind_manifest(view, manifest)
    if wrong_source:
        with pytest.raises(ContractError):
            validate("snapshot_view", view)
    else:
        validate("snapshot_view", view)
