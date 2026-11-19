"""Import attributed compiler diagnostics into a new local snapshot.

GNU JSON diagnostic imports remain imported claims even when their raw report
was locally collected. Empty reports never prove a completed clean analysis.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from cppulse.adapters import gcc_diagnostics as _gcc
from cppulse.adapters.gcc_diagnostics import parse_gcc_json
from cppulse.contracts import validate
from cppulse.errors import ContractError, InputChanged, IntegrityError
from cppulse.identities import digest_json, verify_inputs
from cppulse.run_store import RunSnapshot, RunStore
from cppulse.transfer import ImportedRun


def normalize_external_import(
    snapshot: RunSnapshot | ImportedRun,
    *,
    report_artifact_id: str,
    context_id: str,
    source_root: str,
    scope_files: Sequence[str],
    producer: Mapping[str, str] | None = None,
    adapter: str = "gcc-json",
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
    profiles = {"gcc-json": ("gcc", parse_gcc_json)}
    if adapter != "gcc-json":
        from cppulse.adapters.external_analyzers import (
            parse_clang_tidy_text,
            parse_cppcheck_xml,
        )

        profiles.update(
            {
                "clang-tidy-text": ("clang-tidy", parse_clang_tidy_text),
                "cppcheck-xml": ("cppcheck", parse_cppcheck_xml),
            }
        )
    if adapter not in profiles:
        raise ContractError("Unsupported external diagnostic adapter")
    namespace, parser = profiles[adapter]
    snapshot.verify()
    manifest = snapshot.manifest
    if context_id not in {context["id"] for context in manifest["contexts"]}:
        raise ContractError("Imported diagnostic context is not declared")
    if not set(scope_files) <= {row["path"] for row in manifest["source"]["files"]}:
        raise ContractError("Imported diagnostic scope is outside the source manifest")
    matches = [row for row in manifest["artifacts"] if row["id"] == report_artifact_id]
    if len(matches) != 1:
        raise IntegrityError(
            "Imported report must select one exact declared artifact ID"
        )
    entry = matches[0]
    if entry["size_bytes"] > _gcc.MAX_REPORT_BYTES:
        # The archive verification above SHA-checks this descriptor's bytes
        # without materializing the opaque body. An unavailable adapter result
        # needs that checked identity, not a fabricated parsed payload.
        metadata = parser(
            b"", source_root=source_root, scope_files=scope_files, producer=producer
        )
        report = replace(
            metadata,
            usability="unsupported",
            diagnostics=(),
            report_sha256=entry["sha256"],
            size_bytes=entry["size_bytes"],
            limitations=(
                metadata.limitations[0],
                "Diagnostic report byte limit exceeded; archive identity verified, oversized adapter body was not materialized.",
            ),
        )
    else:
        report = parser(
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
    identifier = namespace + "-import-" + digest_json(identity)
    observations = []
    for index, observation in enumerate(report.diagnostics):
        row = asdict(observation)
        row["id"] = (
            namespace
            + "-occurrence-"
            + digest_json(
                {"fact": identifier, "index": index, "fingerprint": row["fingerprint"]}
            )
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
        "producer_namespace": namespace,
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
    snapshot.verify()
    return result


def persist_external_import(
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
    document = normalize_external_import(snapshot, **selection)
    identifier = document["id"]

    def source_check() -> None:
        snapshot.verify()
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
            "operation": "import-" + document["adapter"]["name"],
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
        manifest["versions"][document["adapter"]["name"] + "-import"] = "1.0.0"
        manifest["limitations"].append(
            "A derived import retains its parent's execution window and imported producer claims; no completed external scan or independent confirmation is inferred."
        )
        result = stage.publish(manifest, source_check=source_check)
    result.verify()
    return result


def normalize_gcc_import(
    snapshot: RunSnapshot | ImportedRun, **selection: Any
) -> dict[str, Any]:
    """Compatibility API for the frozen GNU14.2 JSON import profile."""
    return normalize_external_import(snapshot, **selection, adapter="gcc-json")


def persist_gcc_import(
    snapshot: RunSnapshot, *, workspace: str | Path, store: RunStore, **selection: Any
) -> RunSnapshot:
    """Publish the unchanged GCC profile through the shared import boundary."""
    return persist_external_import(
        snapshot, workspace=workspace, store=store, **selection, adapter="gcc-json"
    )


def external_relationships(
    facts: Sequence[Mapping[str, Any]], native: Sequence[Mapping[str, Any]] = ()
) -> list[dict[str, Any]]:
    """Describe repeated diagnostics/potential location overlap, never confidence.

    A shared line is a candidate relationship, not proof of an equivalent defect.
    Equal imported bytes/fingerprints identify claims, not independent producers.
    Original occurrences remain intact. This index uses linear storage rather than
    constructing a quadratic list of pairwise confirmations.
    """
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for fact in facts:
        for row in fact["observations"]:
            key = (fact["context_id"], row["file"], row["line"])
            groups.setdefault(key, []).append(
                {
                    "fact_id": fact["id"],
                    "observation_id": row["id"],
                    "producer_namespace": fact["producer_namespace"],
                    "origin": "import",
                    "fingerprint": row["fingerprint"],
                    "signature": (
                        fact["producer_namespace"],
                        fact["producer"]["name"],
                        fact["producer"]["version"],
                        row["fingerprint"],
                    ),
                }
            )
    for observations in native:
        for row in observations["items"]:
            key = (row["context_id"], row["file"], row["line"])
            if key in groups:
                groups[key].append(
                    {
                        "fact_id": observations.get("analysis_inventory_id", "native"),
                        "observation_id": row["id"],
                        "producer_namespace": "native",
                        "origin": "native_observation",
                        "fingerprint": row["fingerprint"],
                        "signature": (
                            "native",
                            row["producer"]["name"],
                            row["producer"]["version"],
                            row["fingerprint"],
                        ),
                    }
                )
    result = []
    for (context, file, line), rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        repeated = len({row["signature"] for row in rows}) == 1
        result.append(
            {
                "context_id": context,
                "file": file,
                "line": line,
                "classification": "repeated_diagnostic"
                if repeated
                else "potential_location_overlap",
                "occurrences": [
                    {k: v for k, v in row.items() if k != "signature"} for row in rows
                ],
                "independent_confirmation": False,
                "confidence_adjustment": 0,
            }
        )
    return result
