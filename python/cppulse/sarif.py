"""SARIF 2.1.0 export of checked native occurrences, with explicit partial state.

The official OASIS schema is an offline test reference, not bundled runtime code.
Export runs no analyzer, never refreshes source and never uploads results.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from fractions import Fraction
from typing import Any
from urllib.parse import quote

from cppulse import __version__
from cppulse.contracts import validate
from cppulse.contracts.finding_workflows import ANCHOR_VERSION
from cppulse.contracts.validation import _safe_path
from cppulse.errors import ContractError
from cppulse.findings import (
    MAX_METADATA_BYTES,
    MAX_SOURCE_BYTES,
    _OriginalSnapshot,
    _entry,
    _material,
    _metadata,
)
from cppulse.run_store import RunSnapshot
from cppulse.transfer import ImportedRun

SCHEMA_URI = "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"


def _uri(path: str) -> str:
    _safe_path(path, "/sarif/artifactLocation/uri")
    try:
        return quote(path, safe="/")
    except UnicodeError as error:
        raise ContractError(
            "SARIF source paths must have a valid UTF-8 URI identity"
        ) from error


def _unicode_column(line: bytes, byte_column: int | float | None) -> int | None:
    if byte_column is None:
        return None
    number = Fraction(str(byte_column))
    if number.denominator != 1 or not 1 <= number <= len(line) + 1:
        return None
    try:
        return len(line[: number.numerator - 1].decode("utf-8")) + 1
    except UnicodeError:
        return None


def build_sarif(
    snapshot: RunSnapshot | ImportedRun,
    *,
    comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Export every selected native occurrence without deduplication or execution.

    A supplied comparison must equal a retained typed artifact in this checked
    snapshot, including its closed raw historical roles. It selects the explicit
    scope and may annotate known baseline states. A persisted derived run
    resolves its exact original current manifest; it never labels later facts.
    Suppressed results remain present. Unknown identities get no baselineState.
    """
    if not isinstance(snapshot, (RunSnapshot, ImportedRun)):
        raise ContractError("SARIF export requires a checked local or imported run")
    snapshot.verify()
    source: Any = snapshot
    if comparison is not None:
        comparison = deepcopy(comparison)
        validate("finding_comparison", comparison)
        if comparison["source_digest"] != snapshot.manifest["source"]["digest"]:
            raise ContractError("SARIF comparison describes another owning source")
        if comparison["current_manifest_sha256"] != snapshot.manifest_sha256:
            entry = _entry(snapshot, comparison["current_manifest_artifact_id"])
            if (
                entry["sha256"] != comparison["current_manifest_sha256"]
                or "contract" in entry
            ):
                raise ContractError(
                    "SARIF comparison does not identify retained original current bytes"
                )
            source = _OriginalSnapshot(
                snapshot,
                snapshot.read_bytes(entry["id"]),
                comparison["current_manifest_sha256"],
            )
    bundle, documents = _metadata(source)
    manifest = bundle["run_manifest"]
    inventories = {row["id"]: row for row in bundle.get("analysis_inventory", [])}
    if comparison is not None:
        scope = comparison["scope"]
    else:
        scope = {
            "files": sorted(
                {
                    path
                    for row in inventories.values()
                    for path in row["requested_files"]
                }
            ),
            "context_ids": sorted(
                {row["job_context_id"] for row in inventories.values()}
            ),
            "rule_ids": sorted(
                {
                    rule
                    for row in inventories.values()
                    for rule in row["requested_rules"]
                }
                | {
                    item["rule_id"]
                    for row in bundle.get("observations", [])
                    if row.get("analysis_inventory_id") in inventories
                    for item in row["items"]
                }
            ),
        }
    material = _material(source, scope)
    anchor_by_id = {
        identifier: row
        for row in material.findings
        for identifier in row["observation_ids"]
    }
    occurrences = []
    for artifact_id, document in documents.items():
        if (
            _entry(source, artifact_id).get("contract", {}).get("kind")
            != "observations"
        ):
            continue
        inventory = inventories.get(document.get("analysis_inventory_id"))
        if inventory is None or inventory["job_context_id"] not in scope["context_ids"]:
            continue
        for row in document["items"]:
            if row["file"] in scope["files"] and row["rule_id"] in scope["rule_ids"]:
                occurrences.append((row, inventory["job_context_id"]))
    occurrences.sort(
        key=lambda pair: (
            pair[0]["file"],
            pair[1],
            pair[0]["line"],
            pair[0].get("column", 0),
            pair[0]["rule_id"],
            pair[0]["id"],
        )
    )
    states: dict[str, str] = {}
    suppressed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if comparison is not None:
        linked = {
            identifier
            for group in comparison["groups"]
            for identifier in group["current_observation_ids"]
        }
        if linked != {row["id"] for row, _ in occurrences}:
            raise ContractError(
                "SARIF comparison does not preserve this pinned scope's current occurrences"
            )
        for group in comparison["groups"]:
            identifiers = sorted(group["current_observation_ids"])
            for identifier in identifiers:
                anchor = anchor_by_id[identifier]
                if any(
                    group[field] != anchor[field]
                    for field in ("file", "context_id", "rule_id")
                ):
                    raise ContractError(
                        "SARIF comparison occurrence belongs to another current file/job/rule scope"
                    )
                if (
                    group["fingerprint"] is not None
                    and group["fingerprint"] != anchor["fingerprint"]
                ):
                    raise ContractError(
                        "SARIF comparison fingerprint differs from checked current source anchor"
                    )
            same, introduced = int(group["unchanged_count"]), int(group["new_count"])
            if (same or introduced) and (
                not material.credible.get((group["file"], group["context_id"]), False)
                or any(
                    anchor_by_id[identifier]["anchor_status"] != "unique"
                    for identifier in identifiers
                )
            ):
                raise ContractError(
                    "SARIF known baseline states require credible current source/job facts and unique anchors"
                )
            for identifier in identifiers[:same]:
                states[identifier] = "unchanged"
            new_ids = identifiers[same : same + introduced]
            for identifier in new_ids:
                states[identifier] = "new"
            cursor = 0
            for request in comparison["suppressions"]:
                if not request["active"] or not all(
                    group[key] == request[key]
                    for key in ("file", "context_id", "rule_id", "fingerprint")
                ):
                    continue
                count = int(request["applied_count"])
                selected = new_ids[cursor : cursor + count]
                if len(selected) != count or any(
                    any(
                        request[field] != anchor_by_id[identifier][field]
                        for field in ("parse_context_digest", "rule_version")
                    )
                    for identifier in selected
                ):
                    raise ContractError(
                        "SARIF accepted suppression does not match exact observed context/rule scope"
                    )
                for identifier in selected:
                    suppressed[identifier].append(
                        {
                            "kind": "external",
                            "status": "accepted",
                            "justification": request["reason"],
                            "properties": {
                                "cppulseSuppressionId": request["id"],
                                "ownerClaim": request["owner"],
                                "expiresAt": request["expires_at"],
                                "gate": "finding_regression",
                            },
                        }
                    )
                cursor += count
        retained = [
            entry
            for entry in snapshot.manifest["artifacts"]
            if entry.get("contract")
            == {"kind": "finding_comparison", "version": "2.0.0"}
            and entry["size_bytes"] <= MAX_METADATA_BYTES
            and snapshot.read_json(entry["id"]) == comparison
        ]
        if not retained:
            raise ContractError(
                "SARIF annotations require the exact retained typed finding comparison and checked raw historical roles"
            )
    source_files = {row["path"]: row for row in manifest["source"]["files"]}
    artifacts = []
    indexes = {}
    for path in scope["files"]:
        item: dict[str, Any] = {
            "location": {"uri": _uri(path)},
            "roles": ["analysisTarget"],
        }
        if path in source_files:
            item.update(
                length=int(source_files[path]["size_bytes"]),
                hashes={"sha-256": source_files[path]["sha256"]},
            )
        else:
            item["properties"] = {"cppulseSourceAvailability": "unavailable"}
        indexes[path] = len(artifacts)
        artifacts.append(item)
    registry = {
        row["id"]: row
        for document in bundle.get("rule_registry", [])
        for row in document["rules"]
    }
    selected_rules = sorted(set(scope["rule_ids"]) & set(registry))
    rules = [
        {
            "id": identifier,
            "shortDescription": {"text": registry[identifier]["documentation"]},
            "properties": {
                "cppulseRuleVersion": registry[identifier]["version"],
                "cppulseMaturity": registry[identifier]["maturity"],
                "cppulseCategory": registry[identifier]["category"],
            },
        }
        for identifier in selected_rules
    ]
    rule_indexes = {
        identifier: index for index, identifier in enumerate(selected_rules)
    }
    lines_cache: dict[str, list[bytes] | None] = {}
    cells = {(row["file"], row["context_id"]): row for row in material.cells}
    notifications = [
        {"level": "warning", "message": {"text": reason}} for reason in material.issues
    ]
    results = []
    for observation, job in occurrences:
        path = observation["file"]
        if path not in lines_cache:
            cell = cells[(path, job)]
            identifier = cell["source_artifact_id"]
            lines_cache[path] = (
                source.read_bytes(identifier).splitlines()
                if identifier is not None
                and _entry(source, identifier)["size_bytes"] <= MAX_SOURCE_BYTES
                else None
            )
        region = {"startLine": int(observation["line"])}
        lines = lines_cache[path]
        column = None
        if lines is not None and 1 <= region["startLine"] <= len(lines):
            column = _unicode_column(
                lines[region["startLine"] - 1], observation.get("column")
            )
        if column is not None:
            region["startColumn"] = column
        elif observation.get("column") is not None:
            notifications.append(
                {
                    "level": "warning",
                    "message": {
                        "text": f"A retained byte column could not be converted to Unicode code points: {path}:{observation['line']}; the line is exported without an invented column."
                    },
                }
            )
        anchor = anchor_by_id[observation["id"]]
        fingerprints = {
            "cppulse/" + observation["fingerprint_version"]: observation["fingerprint"]
        }
        if anchor["anchor_status"] == "unique" and anchor["fingerprint"] is not None:
            fingerprints["cppulse/" + ANCHOR_VERSION] = anchor["fingerprint"]
        result: dict[str, Any] = {
            "ruleId": observation["rule_id"],
            "level": {"error": "error", "warning": "warning", "info": "note"}[
                observation["severity"]
            ],
            "message": {"text": observation["message"]},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": _uri(path), "index": indexes[path]},
                        "region": region,
                    }
                }
            ],
            "partialFingerprints": fingerprints,
            "properties": {
                "cppulseObservationId": observation["id"],
                "cppulseJobContextId": job,
                "cppulseParseContextId": observation["context_id"],
                "cppulseRuleVersion": observation["rule_version"],
                "cppulseNativeByteColumn": observation.get("column"),
                "cppulseAnchorStatus": anchor["anchor_status"],
                "cppulseComparisonState": states.get(
                    observation["id"],
                    "unknown" if comparison is not None else "not_compared",
                ),
            },
        }
        if observation["rule_id"] in rule_indexes:
            result["ruleIndex"] = rule_indexes[observation["rule_id"]]
        if observation["id"] in states:
            result["baselineState"] = states[observation["id"]]
        if observation["id"] in suppressed:
            result["suppressions"] = suppressed[observation["id"]]
        results.append(result)
    complete = bool(
        scope["files"]
        and scope["context_ids"]
        and scope["rule_ids"]
        and all(row["status"] == "complete" for row in material.cells)
    )
    if not complete and not notifications:
        notifications.append(
            {
                "level": "warning",
                "message": {
                    "text": "No complete typed native analysis covers the selected source/job/rule scope; zero exported results do not establish a clean analysis."
                },
            }
        )
    if manifest["status"] != "completed":
        notifications.append(
            {
                "level": "warning",
                "message": {
                    "text": f"The original collection status is {manifest['status']}; static-analysis scope and unrelated collection stages remain distinct."
                },
            }
        )
    invocation: dict[str, Any] = {"executionSuccessful": complete}
    if notifications:
        invocation["toolExecutionNotifications"] = notifications
    run = {
        "tool": {"driver": {"name": "cppulse", "version": __version__, "rules": rules}},
        "columnKind": "unicodeCodePoints",
        "artifacts": artifacts,
        "results": results,
        "invocations": [invocation],
        "properties": {
            "cppulseInputRunId": source.run_id,
            "cppulseInputManifestSha256": source.manifest_sha256,
            "cppulseOwningRunId": snapshot.run_id,
            "cppulseSourceDigest": manifest["source"]["digest"],
            "cppulseCollectionStatus": manifest["status"],
            "cppulseInputVerificationClaim": manifest.get(
                "input_verification", "unverified"
            ),
            "cppulseInputOrigin": (
                "import" if isinstance(snapshot, ImportedRun) else "local_retained"
            ),
            "cppulseAuthentication": "unverified",
            "cppulseSourceFreshness": "not_rechecked",
            "cppulseExporterVersion": "1.0.0",
            "cppulseScope": scope,
            "cppulseLimitations": [
                "Every selected native occurrence is exported, including suppressed results; no fingerprint deduplication or policy/raw-score rewrite is performed.",
                "The exporter reads checked retained facts only; it does not execute analysis, recheck current source freshness, authenticate a producer or certify C++ code.",
            ],
        },
    }
    return {"$schema": SCHEMA_URI, "version": "2.1.0", "runs": [run]}
