"""Persist attributed CTest/JUnit imports without inventing a test execution."""

from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from cppulse.adapters.test_results import parse_test_report
from cppulse.contracts import validate
from cppulse.errors import ContractError, InputChanged, IntegrityError
from cppulse.identities import digest_json, verify_inputs
from cppulse.run_store import RunSnapshot, RunStore


def normalize_test_import(
    snapshot: RunSnapshot,
    *,
    report_artifact_id: str,
    context_id: str,
    scope_files: Sequence[str],
    adapter: str,
    producer: Mapping[str, Any],
) -> dict[str, Any]:
    """Read a declared report as imported counts/cases in an explicit context."""
    snapshot.verify()
    manifest = snapshot.manifest
    if context_id not in {c["id"] for c in manifest["contexts"]}:
        raise ContractError("Imported test context is not declared")
    if not set(scope_files) <= {f["path"] for f in manifest["source"]["files"]}:
        raise ContractError("Imported test scope is outside declared source")
    entry = next(
        (a for a in manifest["artifacts"] if a["id"] == report_artifact_id), None
    )
    if entry is None:
        raise IntegrityError("Imported test report is not a declared artifact")
    report = parse_test_report(
        snapshot.path / entry["path"], adapter, producer=dict(producer)
    )
    if report.report_sha256 is not None and (
        report.report_sha256,
        report.size_bytes,
    ) != (entry["sha256"], entry["size_bytes"]):
        raise IntegrityError("Parsed test report differs from retained archive bytes")
    identity = {
        "source_digest": manifest["source"]["digest"],
        "context_id": context_id,
        "report_artifact_id": report_artifact_id,
        "report_sha256": entry["sha256"],
        "scope_files": sorted(scope_files),
        "adapter": adapter,
        "producer": report.producer,
    }
    identifier = "test-import-" + digest_json(identity)
    record = {
        "id": identifier,
        "context_id": context_id,
        "producer": report.producer,
        "origin": "import",
        "kind": "tests",
        "status": report.status,
        "usability": report.usability,
        "artifact_ids": [report_artifact_id],
        "receipt_id": None,
        "scope": {
            "files": sorted(scope_files),
            "tests": [c.identity for c in report.cases],
        },
        "import_adapter": {"name": adapter, "version": report.adapter_version},
        "test_counts": report.counts,
        "test_cases": list(report.as_dict()["cases"]),
        "limitations": [
            *report.limitations,
            "Imported counts and case outcomes do not prove execution, source freshness or producer authenticity. Context attribution is supplied by the caller.",
        ],
    }
    result = {
        "version": "2.0.0",
        "source_digest": manifest["source"]["digest"],
        "records": [record],
    }
    validate("evidence", result)
    snapshot.verify()
    return result


def persist_test_import(
    snapshot: RunSnapshot,
    *,
    workspace: str | Path,
    store: RunStore | Path,
    **selection: Any,
) -> RunSnapshot:
    """Publish a new source-bound archive, retaining the original report bytes."""
    if not isinstance(snapshot, RunSnapshot):
        raise ContractError("Test import publication requires a local RunSnapshot")
    if any(
        a.get("contract", {}).get("kind") == "assessment"
        for a in snapshot.manifest["artifacts"]
    ):
        raise ContractError("Import into the unassessed collection before assessment")
    result = normalize_test_import(snapshot, **selection)
    record = result["records"][0]

    def check() -> None:
        snapshot.verify()
        changed = verify_inputs(Path(workspace), snapshot.manifest["source"])
        if changed:
            raise InputChanged(
                "Local inputs changed before test import: " + "; ".join(changed)
            )

    check()
    identifier = record["id"]
    if any(a["id"] == identifier for a in snapshot.manifest["artifacts"]):
        if snapshot.read_json(identifier) != result:
            raise IntegrityError(
                "Existing imported test identity has different contents"
            )
        check()
        return snapshot
    runtime = store if isinstance(store, RunStore) else RunStore(store)
    with runtime.begin() as stage:
        for entry in snapshot.manifest["artifacts"]:
            copied = stage.copy_artifact(
                entry["id"],
                snapshot.path / entry["path"],
                entry["path"],
                entry["media_type"],
                contract=entry.get("contract"),
            )
            if copied != entry:
                raise IntegrityError(
                    "Original test report archive changed during copying"
                )
        stage.write_json(
            "tests/" + identifier + ".json",
            result,
            contract="evidence",
            artifact_id=identifier,
        )
        manifest = deepcopy(snapshot.manifest)
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        if record["usability"] != "usable" and manifest["status"] == "completed":
            manifest["status"] = "partial"
        manifest["stages"].append(
            {
                "id": identifier,
                "status": "passed" if record["usability"] == "usable" else "error",
                "depends_on": [],
                "reason": "Imported test results; execution and authenticity remain unverified.",
            }
        )
        manifest["versions"]["test-result-import"] = "1.0.0"
        manifest["limitations"].append(record["limitations"][-1])
        child = stage.publish(manifest, source_check=check)
    child.verify()
    return child
