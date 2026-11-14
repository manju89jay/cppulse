"""Import attributed compiler diagnostics into a new local snapshot.

GNU JSON diagnostic imports remain imported claims even when their raw report
was locally collected. Empty reports never prove a completed clean analysis.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from cppulse.adapters.gcc_diagnostics import parse_gcc_json
from cppulse.contracts import validate
from cppulse.errors import ContractError, InputChanged, IntegrityError
from cppulse.identities import digest_json, verify_inputs
from cppulse.run_store import RunSnapshot, RunStore
from cppulse.transfer import ImportedRun


def normalize_gcc_import(
    snapshot: RunSnapshot | ImportedRun,
    *,
    report_artifact_id: str,
    context_id: str,
    source_root: str,
    scope_files: Sequence[str],
    producer: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Normalize checked report bytes, preserving import origin and every occurrence.

    Args:
        snapshot: Original checked local or explicitly imported report archive.
        report_artifact_id: Exact raw report artifact, including captured stderr.
        context_id: Explicit existing job context; this is an attribution claim.
        source_root: Original producer's absolute root used for lexical mapping.
        scope_files: Selected source identities already present in the manifest.
        producer: Imported compiler/version claim, never an execution observation.

    Returns:
        Validated external_analysis_facts with unverified scan completeness.

    Raises:
        ContractError: Invalid scope/context or unsupported metadata.
        IntegrityError: Changed, missing or corrupt snapshot bytes.
    """
    snapshot.verify()
    manifest = snapshot.manifest
    if context_id not in {context["id"] for context in manifest["contexts"]}:
        raise ContractError("Imported diagnostic context is not declared")
    if not set(scope_files) <= {row["path"] for row in manifest["source"]["files"]}:
        raise ContractError("Imported diagnostic scope is outside the source manifest")
    report = parse_gcc_json(
        snapshot.read_bytes(report_artifact_id),
        source_root=source_root,
        scope_files=scope_files,
        producer=producer,
    )
    identity = {
        "source_digest": manifest["source"]["digest"],
        "context_id": context_id,
        "report_artifact_id": report_artifact_id,
        "report_sha256": report.report_sha256,
        "source_root": source_root,
        "scope_files": sorted(scope_files),
        "producer": {"name": report.producer_name, "version": report.producer_version},
        "adapter": {"name": report.adapter, "version": report.adapter_version},
    }
    identifier = "gcc-import-" + digest_json(identity)
    observations = []
    for index, observation in enumerate(report.diagnostics):
        row = asdict(observation)
        row["id"] = "gcc-occurrence-" + digest_json(
            {"fact": identifier, "index": index, "fingerprint": row["fingerprint"]}
        )
        observations.append(row)
    result = {
        "version": "2.0.0",
        "id": identifier,
        "source_digest": manifest["source"]["digest"],
        "context_id": context_id,
        "origin": "import",
        "producer": identity["producer"],
        "adapter": identity["adapter"],
        "producer_namespace": "gcc",
        "report_artifact_id": report_artifact_id,
        "receipt_id": None,
        "producer_version_receipt_id": None,
        "proof_receipt_ids": [],
        "scope_files": sorted(scope_files),
        "scope_completeness": "unverified",
        "usability": report.usability,
        "observations": observations,
        "limitations": [
            *report.limitations,
            "Producer/version and source-root mapping are imported claims. Matching a local source identity does not authenticate this report or prove it analyzed that source.",
            "External occurrences retain their own namespace and are not deduplicated with native findings or independent confirmation.",
        ],
    }
    validate("external_analysis_facts", result)
    return result


def persist_gcc_import(
    snapshot: RunSnapshot,
    *,
    workspace: str | Path,
    store: RunStore,
    **selection: Any,
) -> RunSnapshot:
    """Publish imported facts without rewriting their original report or source.

    An already assessed parent must first select its original collection. Reusing
    a parent assessment as the result of a new snapshot is deliberately refused.
    Source checks concern local selected bytes, not imported report authenticity.
    """
    if not isinstance(snapshot, RunSnapshot):
        raise ContractError(
            "Current-source publication requires a local RunSnapshot; foreign transfer claims remain imported"
        )
    snapshot.verify()
    parent = snapshot.manifest
    if any(
        row.get("contract", {}).get("kind") == "assessment"
        for row in parent["artifacts"]
    ):
        raise ContractError(
            "Import into an unassessed collection, then assess the derived facts"
        )
    document = normalize_gcc_import(snapshot, **selection)
    identifier = document["id"]

    def source_check() -> None:
        issues = verify_inputs(Path(workspace), parent["source"])
        if issues:
            raise InputChanged(
                "Local selected inputs changed before import publication: "
                + "; ".join(issues)
            )

    source_check()
    existing = [row for row in parent["artifacts"] if row["id"] == identifier]
    if existing:
        if snapshot.read_json(identifier) != document:
            raise IntegrityError(
                "An existing external import identity has different contents"
            )
        source_check()
        return snapshot
    with store.begin() as stage:
        for artifact in parent["artifacts"]:
            copied = stage.copy_artifact(
                artifact["id"],
                snapshot.path / artifact["path"],
                artifact["path"],
                artifact["media_type"],
                contract=artifact.get("contract"),
            )
            if copied != artifact:
                raise IntegrityError(
                    "External import changed a parent artifact descriptor"
                )
        stage.write_json(
            "external/" + identifier + ".json",
            document,
            contract="external_analysis_facts",
            artifact_id=identifier,
        )
        derivation = {
            "operation": "import-gcc-json",
            "parent_run_id": snapshot.run_id,
            "parent_manifest_sha256": snapshot.manifest_sha256,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "origin": "import",
            "authentication": "unverified",
            "selection": {
                "report_artifact_id": selection["report_artifact_id"],
                "context_id": selection["context_id"],
                "source_root": selection["source_root"],
                "scope_files": document["scope_files"],
                "producer_claim": document["producer"],
            },
        }
        with tempfile.TemporaryDirectory(prefix="cppulse-gcc-import-") as temporary:
            path = Path(temporary) / "derivation.json"
            path.write_text(
                json.dumps(derivation, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            stage.copy_artifact(
                identifier + ".derivation",
                path,
                "external/" + identifier + "-derivation.json",
                "application/json",
            )
        manifest = deepcopy(parent)
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        available = document["usability"] == "usable"
        if not available and manifest["status"] == "completed":
            manifest["status"] = "partial"
        manifest["stages"].append(
            {
                "id": identifier,
                "status": "passed" if available else "error",
                "depends_on": [],
                "reason": "Imported diagnostics; scan completeness remains unverified. Usability: "
                + document["usability"],
            }
        )
        manifest["versions"]["gcc-json-import"] = "1.0.0"
        manifest["limitations"].append(
            "A derived import retains its parent's execution window and imported producer claims; no completed external scan or independent confirmation is inferred."
        )
        result = stage.publish(manifest, source_check=source_check)
    result.verify()
    return result
