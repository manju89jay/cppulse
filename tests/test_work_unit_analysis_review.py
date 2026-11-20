"""Independent original-receipt and full-scope bridge regressions.

Local repinning below models a self-consistent imported document graph, not a
claim that a filesystem owner cannot replace artifacts or authenticate producers.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from cppulse.contracts import validate_bundle
from cppulse.contracts.work_unit_analysis import validate_work_unit_analysis_bundle
from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes, digest_json
from cppulse.run_store import RunStore
from cppulse.workflows import read_documents
import test_work_unit_analysis as producer_fixtures

published = producer_fixtures.published


@pytest.fixture(scope="module")
def derived(published: Any, tmp_path_factory: pytest.TempPathFactory) -> Any:
    if "analysis_scope" in read_documents(published):
        return published
    from cppulse.work_unit_analysis import persist_work_unit_analysis

    plan = json.loads(published.read_bytes("analysis-plan"))
    return persist_work_unit_analysis(
        published,
        workspace=Path(plan["source_root"]),
        store=RunStore(tmp_path_factory.mktemp("review-derived") / "store"),
    )


def facts(snapshot: Any) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]:
    documents = read_documents(snapshot)
    flat = [
        (kind, document)
        for kind, rows in documents.items()
        if kind != "run_manifest"
        for document in (rows if isinstance(rows, list) else [rows])
    ]
    return deepcopy(flat), deepcopy(snapshot.manifest)


def receipts(flat: list[tuple[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return {doc["id"]: doc for kind, doc in flat if kind == "execution_receipt"}


def test_genuine_original_bridge_documents_validate(derived: Any) -> None:
    validate_bundle(read_documents(derived))
    flat, manifest = facts(derived)
    ids = validate_work_unit_analysis_bundle(flat, manifest, receipts(flat))
    assert len(ids) == 2


@pytest.mark.parametrize("field", ["argv", "cwd"])
def test_changed_receipt_argv_cannot_inherit_old_invocation_context(
    derived: Any, field: str
) -> None:
    flat, manifest = facts(derived)
    binding = next(doc for kind, doc in flat if kind == "work_unit_analysis_binding")
    receipt = binding["result"]["execution_receipt"]
    if field == "argv":
        receipt["argv"].append("--changed-after-original-execution")
    else:
        receipt["cwd"] += "/changed-after-original-execution"
    for kind, document in flat:
        if kind == "execution_receipt" and document["id"] == receipt["id"]:
            document[field] = deepcopy(receipt[field])
        if kind == "analysis_scope":
            for unit in document["units"]:
                execution = unit["execution"]
                if execution and execution["receipt_id"] == receipt["id"]:
                    execution["result_sha256"] = digest_json(binding["result"])
    descriptor = next(
        row
        for row in manifest["artifacts"]
        if row["id"] == binding["result_artifact_id"]
    )
    descriptor.update(
        sha256=digest_json(binding["result"]),
        size_bytes=len(canonical_json_bytes(binding["result"])),
    )
    with pytest.raises(ContractError):
        validate_work_unit_analysis_bundle(flat, manifest, receipts(flat))


def test_missing_peer_forbids_available_global_duplication(derived: Any) -> None:
    from cppulse.contracts.maintenance import validate_maintenance_bundle

    flat, manifest = facts(derived)
    scopes = [doc for kind, doc in flat if kind == "analysis_scope"]
    scope = scopes[0]
    removed = scope["units"][-1]
    removed_unit_id = removed["unit_id"]
    removed.update(
        execution=None,
        outcome="not_attempted",
        parse_status=None,
        reason="Independent missing-peer contract control.",
    )
    removed_inventory_ids = {
        doc["analysis_inventory_id"]
        for kind, doc in flat
        if kind == "work_unit_analysis_binding" and doc["unit_id"] == removed_unit_id
    }
    flat = [
        (kind, doc)
        for kind, doc in flat
        if kind != "maintenance_health"
        and not (
            (kind == "analysis_inventory" and doc["id"] in removed_inventory_ids)
            or (
                kind
                in {"analysis_metrics", "observations", "work_unit_analysis_binding"}
                and doc.get("analysis_inventory_id") in removed_inventory_ids
            )
        )
    ]
    remaining_duplicates = [
        row
        for kind, doc in flat
        if kind == "analysis_metrics"
        for row in doc["items"]
        if row["metric"] in {"duplicate_tokens", "duplicate_lines"}
    ]
    assert remaining_duplicates
    assert all(row["availability"] == "available" for row in remaining_duplicates)
    # An available zero derived when both peers were complete cannot remain a
    # qualified global-duplication fact when one selected peer is now unknown.
    validate_work_unit_analysis_bundle(flat, manifest, receipts(flat))
    with pytest.raises(ContractError):
        validate_maintenance_bundle(flat, manifest)


@pytest.mark.parametrize("gap", ["unverified_inputs", "truncated_inventory"])
def test_global_duplication_requires_complete_declared_inputs(
    derived: Any, gap: str
) -> None:
    from cppulse.contracts.maintenance import validate_maintenance_bundle

    flat, manifest = facts(derived)
    scope = next(doc for kind, doc in flat if kind == "analysis_scope")
    if gap == "unverified_inputs":
        scope["input_verification"] = "unavailable"
    else:
        scope["inventory_complete"] = False
        scope["discovery_gaps"] = ["Selected directory was unreadable."]
    # Isolate available global duplicate facts from any health observation.
    flat = [(kind, doc) for kind, doc in flat if kind != "maintenance_health"]
    with pytest.raises(ContractError):
        validate_maintenance_bundle(flat, manifest)


def test_duplicate_line_count_cannot_exceed_its_physical_source_scope(
    derived: Any,
) -> None:
    from cppulse.contracts import validate

    documents = read_documents(derived)
    measured = deepcopy(documents["analysis_metrics"][0])
    physical = next(row for row in measured["items"] if row["metric"] == "physical_loc")
    duplicate = next(
        row for row in measured["items"] if row["metric"] == "duplicate_lines"
    )
    assert physical["availability"] == duplicate["availability"] == "available"
    duplicate["value"] = physical["value"] + 1
    with pytest.raises(ContractError):
        validate("analysis_metrics", measured)
