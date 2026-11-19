"""Independent compatibility and truthful consumer-fixture integration controls."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from cppulse.analysis import normalize_native_analysis
from cppulse.contracts import validate
from cppulse.errors import CompatibilityError, ContractError
from tests.native_buffer_fixture import add_parsed_buffer_fixture
from test_analysis_inventory import native_snapshot
from test_public_workflow_contracts import run_ref, workflow_document
from test_snapshot_view_contract import display, rebind_assessment, snapshot_view


def native_workflow(*, metrics: bool) -> dict:
    """Use explicitly synthetic output references, not execution attestation."""
    result = workflow_document()
    facts = [
        {"kind": "analysis_inventory", "artifact_id": "inventory", "id": "inventory"},
        {"kind": "observations", "artifact_id": "observations", "id": None},
    ]
    if metrics:
        facts.append({"kind": "analysis_metrics", "artifact_id": "metrics", "id": None})
    result["normalizers"] = [
        {
            "id": "native",
            "kind": "native_analysis",
            "status": "completed",
            "outcome": None,
            "usability": None,
            "fact_artifacts": facts,
            "run": run_ref(),
            "reason": "Synthetic transform result; no execution claim.",
        }
    ]
    return result


@pytest.mark.parametrize("metrics", [False, True])
def test_legacy_and_current_native_result_families_remain_valid(metrics: bool) -> None:
    validate("workflow_result", native_workflow(metrics=metrics))


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_inventory",
        "missing_observations",
        "invented_metric_id",
        "missing_inventory_id",
        "foreign_kind",
        "duplicate_metrics",
    ],
)
def test_native_result_extensions_do_not_relax_required_lineage(mutation: str) -> None:
    result = native_workflow(metrics=True)
    facts = result["normalizers"][0]["fact_artifacts"]
    if mutation == "missing_inventory":
        del facts[0]
    elif mutation == "missing_observations":
        del facts[1]
    elif mutation == "invented_metric_id":
        facts[2]["id"] = "invented-logical-id"
    elif mutation == "missing_inventory_id":
        facts[0]["id"] = None
    elif mutation == "foreign_kind":
        facts.append(
            {"kind": "coverage_facts", "artifact_id": "foreign", "id": "foreign"}
        )
    else:
        facts.append({**facts[2], "artifact_id": "duplicate"})
    with pytest.raises(ContractError):
        validate("workflow_result", result)


def test_local_buffer_fixture_never_upgrades_shared_legacy_or_invents_metrics(
    tmp_path: Path,
) -> None:
    legacy, legacy_selection = native_snapshot(tmp_path / "legacy")
    old = normalize_native_analysis(legacy, **legacy_selection)
    assert old.inventory["items"][0]["buffer_coherence"] == "unverified"
    assert old.metrics is None
    current, selection = native_snapshot(
        tmp_path / "declared", mutate=add_parsed_buffer_fixture
    )
    result = normalize_native_analysis(current, **selection)
    assert result.inventory["items"][0]["buffer_coherence"] == "verified"
    assert result.inventory["items"][0]["context_match"] == "matched"
    assert result.metrics is not None and result.metrics["items"]
    assert all(
        cell["availability"] == "unavailable" and cell["value"] is None
        for cell in result.metrics["items"]
    )


def test_buffer_fixture_cannot_promote_unverified_execution_binding(
    tmp_path: Path,
) -> None:
    raw, selection = native_snapshot(
        tmp_path, mutate=add_parsed_buffer_fixture, verified=False
    )
    with pytest.raises(CompatibilityError, match="source-verified"):
        normalize_native_analysis(raw, **selection)


@pytest.mark.parametrize("marker", [None, "tu-buffer-coherence-v1"])
def test_exact_assessment_marker_and_legacy_display_preserve_stored_document(
    marker: str | None,
) -> None:
    view = snapshot_view()
    document = json.loads(view["assessment"]["raw_json"])
    if marker is not None:
        document["native_input_binding"] = marker
    rebind_assessment(view, document)
    view["assessment"]["display"] = display(document)
    validate("snapshot_view", view)
    if marker is not None:
        altered = deepcopy(view)
        altered["assessment"]["display"]["native_input_binding"] = "invented-binding"
        with pytest.raises(ContractError):
            validate("snapshot_view", altered)
