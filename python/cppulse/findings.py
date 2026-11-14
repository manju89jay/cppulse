"""Checked source-line baselines and scoped regression checks, without execution.

The explicit anchor strategy compares retained byte lines, not C++ semantics.
Historical inputs remain unauthenticated claims. Current source freshness and
publication are separate workflow responsibilities; no live project is read.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from typing import Any

from cppulse.consumer import RetainedBlob, _manifest_bytes
from cppulse.contracts import validate, validate_bundle
from cppulse.contracts.finding_workflows import (
    ANCHOR_VERSION,
    PRODUCER,
    anchor_fingerprint,
    scope_identity,
)
from cppulse.errors import ContractError, IntegrityError
from cppulse.run_store import Contract, RunSnapshot
from cppulse.transfer import ImportedRun

MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
_LIMITS = [
    "This is an anchored observation comparison over finite selected source/job/rule facts, not a defect-equivalence, certification or safety claim.",
    "Historical baseline, execution and source fields remain unauthenticated retained claims. Current source freshness is not rechecked by this pure producer.",
    "Exact byte-line anchors support unique unchanged lines; whitespace/token edits, repeated lines and unsupported context relocation may remain unknown. No context arguments are stripped or silently migrated.",
    "Dependencies require fresh full fact collection; this comparison does not implement incremental analysis, dependency discovery or cache reuse.",
]


@dataclass(frozen=True)
class FindingResult:
    """A validated document and generic raw roles for a separate checked writer."""

    document: dict[str, Any]
    artifacts: tuple[RetainedBlob, ...]


@dataclass(frozen=True)
class _Material:
    scope: dict[str, Any]
    cells: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    observation_artifact_ids: list[str]
    credible: dict[tuple[str, str], bool]
    issues: list[str]


def _encoded(document: Any) -> bytes:
    return (
        json.dumps(
            document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode()


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json(content: bytes, name: str) -> dict[str, Any]:
    if len(content) > MAX_METADATA_BYTES:
        raise IntegrityError(f"Finding metadata exceeds its byte bound: {name}")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value

    def constant(value: str) -> None:
        raise ValueError("Nonfinite JSON is not a finding document")

    try:
        result = json.loads(content, object_pairs_hook=pairs, parse_constant=constant)
        json.dumps(result, allow_nan=False)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise IntegrityError(f"Invalid finite finding JSON: {name}") from error
    if not isinstance(result, dict):
        raise IntegrityError(f"Finding metadata must be a JSON object: {name}")
    return result


def _time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as error:
        raise ContractError(
            "Finding workflows require an explicit UTC timestamp"
        ) from error
    if result.utcoffset() != timedelta(0):
        raise ContractError("Finding workflows require an explicit UTC timestamp")
    return result


def _blob(
    role: str, content: bytes, media_type: str = "application/json"
) -> RetainedBlob:
    identifier = "finding-" + role + "-" + _sha(content)
    return RetainedBlob(
        identifier,
        "findings/imports/"
        + identifier
        + (".json" if media_type == "application/json" else ".bin"),
        content,
        media_type,
    )


def _entry(snapshot: Any, name: str) -> dict[str, Any]:
    entries = [
        row
        for row in snapshot.manifest["artifacts"]
        if name in {row["id"], row["path"]}
    ]
    if len(entries) != 1:
        raise ContractError(f"Finding artifact is absent or ambiguous: {name!r}")
    return entries[0]


def _metadata(snapshot: Any) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    snapshot.verify()
    bundle: dict[str, Any] = {"run_manifest": snapshot.manifest}
    documents = {}
    for entry in snapshot.manifest["artifacts"]:
        reference = entry.get("contract", {})
        if reference.get("version") != "2.0.0":
            continue
        if entry["size_bytes"] > MAX_METADATA_BYTES:
            raise IntegrityError(
                "Retained finding control document exceeds metadata cap"
            )
        document = _json(snapshot.read_bytes(entry["id"]), entry["path"])
        validate(reference["kind"], document)
        documents[entry["id"]] = document
        if reference["kind"] == "policy":
            bundle["policy"] = document
        else:
            bundle.setdefault(reference["kind"], []).append(document)
    validate_bundle(bundle)
    return bundle, documents


class _OriginalSnapshot:
    """Read an original retained manifest through checked descendant/import bytes."""

    def __init__(
        self, backing: RunSnapshot | ImportedRun, content: bytes, sha256: str
    ) -> None:
        if _sha(content) != sha256:
            raise IntegrityError("Original finding manifest digest mismatch")
        self._backing = backing
        self._raw = content
        self._manifest = _json(content, "original run manifest")
        validate("run_manifest", self._manifest)
        self.run_id = self._manifest["run_id"]
        self.manifest_sha256 = sha256
        available = {row["id"]: row for row in backing.manifest["artifacts"]}
        if any(available.get(row["id"]) != row for row in self._manifest["artifacts"]):
            raise IntegrityError(
                "Original finding manifest artifacts were changed or not retained"
            )

    @property
    def manifest(self) -> dict[str, Any]:
        return deepcopy(self._manifest)

    def read_bytes(self, name: str) -> bytes:
        entry = _entry(self, name)
        content = self._backing.read_bytes(entry["id"])
        if len(content) != entry["size_bytes"] or _sha(content) != entry["sha256"]:
            raise IntegrityError("Original finding artifact changed")
        return content

    def read_json(
        self, name: str, *, contract: Contract | None = None
    ) -> dict[str, Any]:
        entry = _entry(self, name)
        document = _json(self.read_bytes(name), entry["path"])
        reference = entry.get("contract") if contract is None else contract
        if isinstance(reference, str):
            validate(reference, document)
        elif isinstance(reference, dict):
            validate(reference["kind"], document, version=reference["version"])
        else:
            raise ContractError("Original finding JSON needs a declared contract")
        return document

    def verify(self) -> None:
        # The backing reader verifies each returned buffer; validate every
        # original contracted document without consulting a vanished checkout.
        bundle: dict[str, Any] = {"run_manifest": self.manifest}
        for entry in self._manifest["artifacts"]:
            content = self.read_bytes(entry["id"])
            reference = entry.get("contract", {})
            if reference.get("version") != "2.0.0":
                continue
            document = _json(content, entry["path"])
            validate(reference["kind"], document)
            if reference["kind"] == "policy":
                bundle["policy"] = document
            else:
                bundle.setdefault(reference["kind"], []).append(document)
        validate_bundle(bundle)


def _scope(
    scope_files: Sequence[str], context_ids: Sequence[str], rule_ids: Sequence[str]
) -> dict[str, Any]:
    validate(
        "finding_baseline_request",
        {
            "version": "2.0.0",
            "baseline_id": "selection",
            "scope_files": list(scope_files),
            "context_ids": list(context_ids),
            "rule_ids": list(rule_ids),
            "reason": "Explicit selected finding scope",
        },
    )
    result = {
        "files": sorted(scope_files),
        "context_ids": sorted(context_ids),
        "rule_ids": sorted(rule_ids),
    }
    return {**result, "sha256": scope_identity(result)}


def _material(snapshot: Any, scope: dict[str, Any]) -> _Material:
    bundle, documents = _metadata(snapshot)
    manifest = bundle["run_manifest"]
    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    sources = {row["path"]: row for row in manifest["source"]["files"]}
    contexts = {row["id"]: row for row in manifest["contexts"]}
    inventories = {row["id"]: row for row in bundle.get("analysis_inventory", [])}
    executions = {
        row["receipt"]["id"]: row for row in bundle.get("execution_facts", [])
    }
    cells, credibility, issues = [], {}, []
    by_cell = {}
    for path in scope["files"]:
        for job in scope["context_ids"]:
            key = (path, job)
            candidates = [
                row
                for row in inventories.values()
                if row["job_context_id"] == job and path in row["requested_files"]
            ]
            cell: dict[str, Any] = {
                "file": path,
                "context_id": job,
                "parse_context_digest": None,
                "inventory_id": None,
                "source_artifact_id": None,
                "source_sha256": sources.get(path, {}).get("sha256"),
                "registry_sha256": None,
                "config_sha256": None,
                "native_executable_sha256": None,
                "status": "unavailable",
                "executed_rules": [],
            }
            credible = False
            if len(candidates) == 1:
                inventory = candidates[0]
                row = next(item for item in inventory["items"] if item["file"] == path)
                execution = executions.get(inventory["receipt_id"])
                context = contexts.get(row["parse_context_id"])
                cell.update(
                    inventory_id=inventory["id"],
                    parse_context_digest=context["digest"] if context else None,
                    registry_sha256=inventory["registry_sha256"],
                    config_sha256=artifacts[inventory["config_artifact_id"]]["sha256"],
                    native_executable_sha256=(
                        execution["executable_fact"]["sha256"]
                        if execution and execution["executable_fact"]
                        else None
                    ),
                    status="incomplete",
                    executed_rules=sorted(row["executed_rules"]),
                )
                source = sources.get(path)
                links = (
                    []
                    if execution is None
                    else [
                        item["artifact_id"]
                        for item in execution["binding"]["input_artifacts"]
                        if item["path"] == path
                        and source
                        and all(
                            artifacts[item["artifact_id"]][name] == source[name]
                            for name in ("sha256", "size_bytes")
                        )
                    ]
                )
                if links:
                    cell["source_artifact_id"] = sorted(links)[0]
                credible = bool(
                    manifest.get("input_verification") == "verified"
                    and execution
                    and execution["binding"]["status"] == "verified"
                    and execution["material_status"] == "available"
                    and execution["receipt"]["status"] == "passed"
                    and row["status"] in {"analyzed", "partial"}
                    and row["context_match"] == "matched"
                    and inventory.get("compilation_database_artifact_id") is not None
                    and inventory.get("resource_manifest_artifact_id") is not None
                    and cell["source_artifact_id"] is not None
                )
                if (
                    credible
                    and row["status"] == "analyzed"
                    and row["error_count"] == 0
                    and set(scope["rule_ids"])
                    <= set(inventory["requested_rules"]) & set(row["executed_rules"])
                ):
                    cell["status"] = "complete"
            if cell["source_artifact_id"] is None and path in sources:
                matches = [
                    item["id"]
                    for item in artifacts.values()
                    if all(
                        item[name] == sources[path][name]
                        for name in ("sha256", "size_bytes")
                    )
                ]
                if matches:
                    cell["source_artifact_id"] = sorted(matches)[0]
            if cell["status"] != "complete":
                issues.append(
                    f"Incomplete selected native rule consideration: {path} in job {job}"
                )
            cells.append(cell)
            by_cell[key] = cell
            credibility[key] = credible
    source_cache: dict[str, tuple[list[bytes], Counter[bytes]] | None] = {}

    def line_anchor(
        cell: dict[str, Any], observation: dict[str, Any]
    ) -> tuple[str | None, str]:
        path = cell["file"]
        if path not in source_cache:
            identifier = cell["source_artifact_id"]
            if (
                identifier is None
                or artifacts[identifier]["size_bytes"] > MAX_SOURCE_BYTES
            ):
                source_cache[path] = None
                issues.append(
                    f"Retained anchor source is missing or exceeds {MAX_SOURCE_BYTES} bytes: {path}"
                )
            else:
                content = snapshot.read_bytes(identifier)
                if _sha(content) != cell["source_sha256"]:
                    raise IntegrityError(
                        "Anchor source bytes differ from selected source identity"
                    )
                lines = content.splitlines()
                source_cache[path] = (lines, Counter(lines))
        cached = source_cache[path]
        if cached is None:
            return None, "unavailable"
        lines, counts = cached
        number = int(observation["line"])
        if not 1 <= number <= len(lines):
            raise ContractError(
                "Finding location lies outside its checked retained source"
            )
        line = lines[number - 1]
        column = observation.get("column")
        if column is not None and not 1 <= int(column) <= len(line) + 1:
            raise ContractError(
                "Finding byte column lies outside its checked source line"
            )
        return _sha(line), "unique" if counts[line] == 1 else "ambiguous"

    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    used_documents = []
    for artifact_id, document in documents.items():
        if artifacts[artifact_id].get("contract", {}).get("kind") != "observations":
            continue
        inventory = inventories.get(document.get("analysis_inventory_id"))
        if inventory is None or inventory["job_context_id"] not in scope["context_ids"]:
            continue
        selected = False
        for observation in document["items"]:
            if (
                observation["file"] not in scope["files"]
                or observation["rule_id"] not in scope["rule_ids"]
            ):
                continue
            selected = True
            cell = by_cell[(observation["file"], inventory["job_context_id"])]
            anchor, status = line_anchor(cell, observation)
            item = {
                "file": observation["file"],
                "context_id": inventory["job_context_id"],
                "parse_context_digest": cell["parse_context_digest"],
                "producer": deepcopy(observation["producer"]),
                "rule_id": observation["rule_id"],
                "rule_version": observation["rule_version"],
                "severity": observation["severity"],
                "message": observation["message"],
                "column": observation.get("column"),
                "anchor_sha256": anchor,
                "anchor_status": status,
            }
            item["fingerprint"] = anchor_fingerprint(item)
            group_key = (
                item["file"],
                item["context_id"],
                item["rule_id"],
                item["fingerprint"],
                item["message"],
                item["column"],
            )
            row = groups.setdefault(
                group_key, {**item, "count": 0, "observation_ids": []}
            )
            row["count"] += 1
            row["observation_ids"].append(observation["id"])
            if status != "unique":
                issues.append(
                    f"{status.capitalize()} source-line anchor: {item['file']} in job {item['context_id']}"
                )
        if selected or not document["items"]:
            used_documents.append(artifact_id)
    findings = sorted(
        groups.values(),
        key=lambda row: (
            row["file"],
            row["context_id"],
            row["rule_id"],
            row["fingerprint"] or "",
            row["message"],
            row["column"] or 0,
        ),
    )
    for row in findings:
        row["observation_ids"].sort()
    return _Material(
        scope, cells, findings, sorted(used_documents), credibility, sorted(set(issues))
    )


def _preview(snapshot: Any, kind: str, result: FindingResult) -> None:
    bundle, _ = _metadata(snapshot)
    known = {row["id"]: row for row in bundle["run_manifest"]["artifacts"]}
    for blob in result.artifacts:
        descriptor = blob.descriptor()
        if blob.id in known and known[blob.id] != descriptor:
            raise IntegrityError(
                "Finding raw artifact identity collides with existing data"
            )
        if blob.id not in known:
            bundle["run_manifest"]["artifacts"].append(descriptor)
            known[blob.id] = descriptor
    bundle.setdefault(kind, []).append(result.document)
    validate_bundle(bundle)


def create_finding_baseline(
    snapshot: RunSnapshot,
    *,
    baseline_id: str,
    scope_files: Sequence[str],
    context_ids: Sequence[str],
    rule_ids: Sequence[str],
    reason: str,
    created_at: str,
) -> FindingResult:
    """Create an explicit anchored multiset from checked retained source bytes.

    This does not publish, execute, suppress raw observations or refresh source.
    A baseline can retain incomplete cells; creation is not a passing check.
    """
    if not isinstance(snapshot, RunSnapshot):
        raise ContractError("Baseline creation requires a local retained RunSnapshot")
    validate(
        "finding_baseline_request",
        {
            "version": "2.0.0",
            "baseline_id": baseline_id,
            "scope_files": list(scope_files),
            "context_ids": list(context_ids),
            "rule_ids": list(rule_ids),
            "reason": reason,
        },
    )
    if _time(created_at) < _time(snapshot.manifest["finished_at"]):
        raise ContractError("Baseline creation predates its selected input run")
    material = _material(snapshot, _scope(scope_files, context_ids, rule_ids))
    raw = _blob("original-manifest", _manifest_bytes(snapshot))
    document = {
        "version": "2.0.0",
        "id": baseline_id,
        "producer": dict(PRODUCER),
        "source_digest": snapshot.manifest["source"]["digest"],
        "original_run_id": snapshot.run_id,
        "original_manifest_sha256": snapshot.manifest_sha256,
        "original_manifest_artifact_id": raw.id,
        "observations_artifact_ids": material.observation_artifact_ids,
        "created_at": created_at,
        "reason": reason,
        "fingerprint_version": ANCHOR_VERSION,
        "scope": material.scope,
        "config_digest": snapshot.manifest["config_digest"],
        "cells": material.cells,
        "findings": material.findings,
        "limitations": [*_LIMITS, *material.issues],
    }
    validate("finding_baseline", document)
    result = FindingResult(document, (raw,))
    _preview(snapshot, "finding_baseline", result)
    return result


def _same_material(baseline: dict[str, Any], material: _Material) -> bool:
    # Array order is not part of a multiset/scope identity.
    def canonical(rows: list[dict[str, Any]], key: str | None = None) -> list[str]:
        values = deepcopy(rows)
        for row in values:
            for field in [key] if key else []:
                row[field] = sorted(row[field])
            for field in ("column", "count"):
                if field in row and row[field] is not None:
                    row[field] = int(row[field])
        return sorted(
            json.dumps(row, sort_keys=True, ensure_ascii=False) for row in values
        )

    cells = deepcopy(baseline["cells"])
    expected = deepcopy(material.cells)
    return (
        baseline["scope"]["sha256"] == material.scope["sha256"]
        and canonical(cells, "executed_rules") == canonical(expected, "executed_rules")
        and canonical(baseline["findings"], "observation_ids")
        == canonical(material.findings, "observation_ids")
        and set(baseline["observations_artifact_ids"])
        == set(material.observation_artifact_ids)
    )


def compare_findings(
    current: RunSnapshot,
    baseline_snapshot: RunSnapshot | ImportedRun,
    *,
    baseline_artifact_id: str,
    scope_files: Sequence[str],
    context_ids: Sequence[str],
    rule_ids: Sequence[str],
    generated_at: str,
    rename_map: Mapping[str, str] | Sequence[Mapping[str, str]] | None = None,
    suppressions: Sequence[Mapping[str, Any]] = (),
    suppression_bytes: bytes | None = None,
    max_new: int = 0,
    comparison_id: str | None = None,
) -> FindingResult:
    """Compare pinned historical anchors with independently retained current facts.

    Raw current/baseline counts stay visible. Suppressions apply only known new
    occurrences in this finding check; policy/native observations are untouched.
    """
    if not isinstance(current, RunSnapshot) or not isinstance(
        baseline_snapshot, (RunSnapshot, ImportedRun)
    ):
        raise ContractError(
            "Finding checks require a local current run and a checked historical baseline root"
        )
    now = _time(generated_at)
    scope = _scope(scope_files, context_ids, rule_ids)
    renames = (
        [{"from": old, "to": new} for old, new in rename_map.items()]
        if isinstance(rename_map, Mapping)
        else [dict(row) for row in (rename_map or [])]
    )
    validate(
        "finding_check_request",
        {
            "version": "2.0.0",
            "baseline": {
                "source": "local_run",
                "store": ".",
                "run_id": "selected",
                "manifest_sha256": "0" * 64,
                "artifact_id": baseline_artifact_id,
            },
            "scope_files": list(scope_files),
            "context_ids": list(context_ids),
            "rule_ids": list(rule_ids),
            "max_new": max_new,
            "rename_map": renames,
        },
    )
    if now < _time(current.manifest["finished_at"]):
        raise ContractError("Finding comparison predates the selected current run")
    baseline_snapshot.verify()
    selected = _entry(baseline_snapshot, baseline_artifact_id)
    if selected["size_bytes"] > MAX_METADATA_BYTES:
        raise IntegrityError("Baseline JSON exceeds finding metadata cap")
    baseline_bytes = baseline_snapshot.read_bytes(baseline_artifact_id)
    baseline = _json(baseline_bytes, "finding baseline")
    validate("finding_baseline", baseline)
    if now < _time(baseline["created_at"]):
        raise ContractError("Finding comparison predates baseline creation")
    if baseline["source_digest"] != baseline_snapshot.manifest["source"]["digest"]:
        raise ContractError(
            "Select the baseline's original owning root, not a foreign raw copy in another source namespace"
        )
    original_bytes = baseline_snapshot.read_bytes(
        baseline["original_manifest_artifact_id"]
    )
    original = _OriginalSnapshot(
        baseline_snapshot, original_bytes, baseline["original_manifest_sha256"]
    )
    if (
        original.run_id != baseline["original_run_id"]
        or original.manifest["source"]["digest"] != baseline["source_digest"]
        or original.manifest["config_digest"] != baseline["config_digest"]
    ):
        raise IntegrityError(
            "Baseline original run/source/config identity differs from retained manifest bytes"
        )
    before = _material(original, baseline["scope"])
    if not _same_material(baseline, before):
        raise IntegrityError(
            "Baseline anchors/cells do not match retained original source and native facts"
        )
    after = _material(current, scope)
    mapping = {row["from"]: row["to"] for row in renames}
    if not set(mapping) <= set(before.scope["files"]) or not set(
        mapping.values()
    ) <= set(scope["files"]):
        raise ContractError(
            "Explicit rename mapping must select original and current canonical scope paths"
        )
    mapped_files = [mapping.get(path, path) for path in before.scope["files"]]
    if len(mapped_files) != len(set(mapped_files)):
        raise ContractError("Explicit rename mapping aliases another original path")
    same_scope = (
        set(mapped_files) == set(scope["files"])
        and set(before.scope["context_ids"]) == set(scope["context_ids"])
        and set(before.scope["rule_ids"]) == set(scope["rule_ids"])
    )
    issues = [*before.issues, *after.issues]
    if not same_scope:
        issues.append(
            "Selected path/job/rule scope differs from the baseline after explicit rename mapping; only requested historical occurrences are counted"
        )
    old_cells = {
        (mapping.get(row["file"], row["file"]), row["context_id"]): row
        for row in before.cells
    }
    new_cells = {(row["file"], row["context_id"]): row for row in after.cells}
    comparable = {}
    incomplete = not same_scope or bool(before.issues or after.issues)
    for key, cell in new_cells.items():
        old = old_cells.get(key)
        dimensions = (
            "parse_context_digest",
            "registry_sha256",
            "config_sha256",
            "native_executable_sha256",
        )
        compatible = bool(
            same_scope
            and old
            and all(
                old[field] is not None and old[field] == cell[field]
                for field in dimensions
            )
            and before.credible.get((old["file"], key[1]), False)
            and after.credible[key]
        )
        comparable[key] = compatible
        if not compatible:
            issues.append(
                f"Source/job context, detector configuration, registry, tool or source binding is not exactly comparable: {key[0]} in job {key[1]}"
            )
            incomplete = True
        if old is None or old["status"] != "complete" or cell["status"] != "complete":
            incomplete = True
    old_groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in before.findings:
        path = mapping.get(row["file"], row["file"])
        if (
            path not in scope["files"]
            or row["context_id"] not in scope["context_ids"]
            or row["rule_id"] not in scope["rule_ids"]
        ):
            continue
        expected = anchor_fingerprint({**row, "file": path})
        key = (path, row["context_id"], row["rule_id"], expected or "")
        if key in old_groups:
            # No hash is invented for unavailable identities: retain the whole
            # unknown multiset under one cell/rule group.
            old_groups[key]["observation_ids"].extend(row["observation_ids"])
            old_groups[key]["count"] += row["count"]
        else:
            old_groups[key] = deepcopy(row)
    new_groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in after.findings:
        key = (row["file"], row["context_id"], row["rule_id"], row["fingerprint"] or "")
        if key in new_groups:
            new_groups[key]["observation_ids"].extend(row["observation_ids"])
            new_groups[key]["count"] += row["count"]
        else:
            new_groups[key] = deepcopy(row)
    groups = []
    for key in sorted(set(old_groups) | set(new_groups)):
        path, job, rule, _ = key
        old, new = old_groups.get(key), new_groups.get(key)
        old_ids = sorted(old["observation_ids"]) if old else []
        new_ids = sorted(new["observation_ids"]) if new else []
        c, b = len(new_ids), len(old_ids)
        unique = (old is None or old["anchor_status"] == "unique") and (
            new is None or new["anchor_status"] == "unique"
        )
        known = comparable.get((path, job), False) and unique
        same = min(c, b) if known else 0
        old_complete = old_cells.get((path, job), {}).get("status") == "complete"
        current_complete = new_cells[(path, job)]["status"] == "complete"
        introduced = c - same if known and old_complete else 0
        resolved = b - same if known and current_complete else 0
        unknown_c, unknown_b = c - same - introduced, b - same - resolved
        if unknown_c or unknown_b:
            incomplete = True
        groups.append(
            {
                "file": path,
                "context_id": job,
                "rule_id": rule,
                "fingerprint": new["fingerprint"] if new else None,
                "baseline_fingerprint": old["fingerprint"] if old else None,
                "current_observation_ids": new_ids,
                "baseline_observation_ids": old_ids,
                "new_count": introduced,
                "unchanged_count": same,
                "resolved_count": resolved,
                "unknown_current_count": unknown_c,
                "unknown_baseline_count": unknown_b,
                "suppressed_count": 0,
                "reason": (
                    "Unique checked source-line identity under exact observed context/configuration"
                    if known
                    else "Unknown anchor or incompatible/incomplete retained source/job context; occurrences were not hidden"
                ),
            }
        )
    raw_requests = [deepcopy(dict(row)) for row in suppressions]
    if suppression_bytes is not None:
        supplied = _json(suppression_bytes, "finding suppression requests")
        validate("finding_suppressions", supplied)
        if raw_requests and raw_requests != supplied["records"]:
            raise ContractError(
                "Suppression bytes differ from selected request records"
            )
        raw_requests = supplied["records"]
    validate("finding_suppressions", {"version": "2.0.0", "records": raw_requests})
    applied = []
    baseline_sha = _sha(baseline_bytes)
    for request in raw_requests:
        reason = None
        targets = [
            row
            for row in groups
            if all(
                row[field] == request[field]
                for field in ("file", "context_id", "rule_id", "fingerprint")
            )
            and row["new_count"] > row["suppressed_count"]
        ]
        cell = new_cells.get((request["file"], request["context_id"]))
        matching_material = [
            row
            for row in after.findings
            if all(
                row[field] == request[field]
                for field in (
                    "file",
                    "context_id",
                    "rule_id",
                    "fingerprint",
                    "rule_version",
                )
            )
        ]
        if request["baseline_sha256"] != baseline_sha:
            reason = "Suppression names another exact baseline artifact"
        elif _time(request["approved_at"]) > now or _time(request["expires_at"]) <= now:
            reason = "Suppression is not effective at this comparison time"
        elif (
            cell is None
            or cell["parse_context_digest"] != request["parse_context_digest"]
            or not matching_material
            or not targets
        ):
            reason = "No eligible known new occurrence matches the exact file/job/context/rule/fingerprint scope"
        count = 0
        if reason is None:
            if len(targets) != 1:
                raise ContractError(
                    "Suppression scope is ambiguous across finding groups"
                )
            target = targets[0]
            count = min(
                int(request["max_count"]),
                target["new_count"] - target["suppressed_count"],
            )
            target["suppressed_count"] += count
        applied.append(
            {
                **request,
                "active": count > 0,
                "applied_count": count,
                "inactive_reason": reason,
            }
        )
    counts = {
        "current": sum(len(row["current_observation_ids"]) for row in groups),
        "baseline": sum(len(row["baseline_observation_ids"]) for row in groups),
    }
    counts.update(
        {
            name: sum(row[field] for row in groups)
            for name, field in [
                ("new", "new_count"),
                ("unchanged", "unchanged_count"),
                ("resolved", "resolved_count"),
                ("unknown_current", "unknown_current_count"),
                ("unknown_baseline", "unknown_baseline_count"),
                ("suppressed_new", "suppressed_count"),
            ]
        }
    )
    counts["unsuppressed_new"] = counts["new"] - counts["suppressed_new"]
    raw_baseline = _blob("baseline", baseline_bytes)
    raw_original = _blob("baseline-manifest", original_bytes)
    raw_current = _blob("current-manifest", _manifest_bytes(current))
    blobs = [raw_baseline, raw_original, raw_current]
    suppression_blob = None
    if raw_requests or suppression_bytes is not None:
        suppression_blob = _blob(
            "suppression-requests",
            (
                suppression_bytes
                if suppression_bytes is not None
                else _encoded({"version": "2.0.0", "records": raw_requests})
            ),
        )
        blobs.append(suppression_blob)
    # Keep selected old source/observation bytes independently auditable, without
    # merging their typed primary-source namespace into the new run.
    old_roles = {
        row["source_artifact_id"]
        for row in before.cells
        if row["source_artifact_id"] is not None
    } | set(before.observation_artifact_ids)
    for identifier in sorted(old_roles):
        entry = _entry(original, identifier)
        if entry["size_bytes"] <= MAX_SOURCE_BYTES:
            blobs.append(
                _blob(
                    "baseline-material",
                    original.read_bytes(identifier),
                    "application/octet-stream",
                )
            )
    all_comparable = (
        same_scope
        and all(comparable.values())
        and all(
            row["anchor_status"] == "unique"
            for row in [*before.findings, *after.findings]
        )
    )
    gate = (
        "failed"
        if counts["unsuppressed_new"] > max_new
        else (
            "insufficient_evidence"
            if incomplete or not all_comparable or not scope["files"]
            else "passed"
        )
    )
    document = {
        "version": "2.0.0",
        "id": comparison_id
        or "finding-comparison-"
        + _sha((current.manifest_sha256 + baseline_sha + generated_at).encode()),
        "producer": dict(PRODUCER),
        "source_digest": current.manifest["source"]["digest"],
        "current_manifest_sha256": current.manifest_sha256,
        "current_manifest_artifact_id": raw_current.id,
        "baseline_artifact_id": raw_baseline.id,
        "baseline_sha256": baseline_sha,
        "baseline_manifest_artifact_id": raw_original.id,
        "baseline_manifest_sha256": baseline["original_manifest_sha256"],
        "fingerprint_version": ANCHOR_VERSION,
        "generated_at": generated_at,
        "scope": scope,
        "rename_map": renames,
        "max_new": max_new,
        "gate": gate,
        "comparable": all_comparable,
        "incomplete": incomplete,
        "counts": counts,
        "groups": groups,
        "suppressions_artifact_id": suppression_blob.id if suppression_blob else None,
        "suppressions_sha256": (
            _sha(suppression_blob.content) if suppression_blob else None
        ),
        "suppressions": applied,
        "issues": sorted(set(issues)),
        "limitations": list(_LIMITS),
    }
    validate("finding_comparison", document)
    result = FindingResult(document, tuple({blob.id: blob for blob in blobs}.values()))
    _preview(current, "finding_comparison", result)
    return result
