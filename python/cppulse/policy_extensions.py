"""Pure numeric and declared-review predicates for explicit evaluator profile 1.2.

Numeric aggregation is confined to one source file in one declared job. Review
quorums count configured distinct identifiers, never authenticated people.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Any


@dataclass(frozen=True)
class ExtensionResult:
    """A raw predicate result before source and prerequisite gating."""

    status: str
    incomplete: bool
    reason: str
    evidence_ids: tuple[str, ...]
    references: tuple[str, ...]
    fact_ids: tuple[str, ...] = ()


def _documents(bundle: Mapping[str, Any], kind: str) -> list[dict[str, Any]]:
    value = bundle.get(kind, [])
    return value if isinstance(value, list) else [value]


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))


def _meets(value: Fraction, operator: str, threshold: Fraction) -> bool:
    return {
        "lt": value < threshold,
        "lte": value <= threshold,
        "eq": value == threshold,
        "gte": value >= threshold,
        "gt": value > threshold,
    }[operator]


def _inventory_references(inventory: dict[str, Any]) -> set[str]:
    return {
        f"analysis_inventory:{inventory['id']}",
        f"receipt:{inventory['receipt_id']}",
        *[
            f"artifact:{inventory[key]}"
            for key in (
                "report_artifact_id", "registry_artifact_id", "config_artifact_id",
                "compilation_database_artifact_id", "resource_manifest_artifact_id",
            )
            if inventory.get(key) is not None
        ],
    }


def _observed(
    inventory: dict[str, Any], row: dict[str, Any], executions: dict[str, Any]
) -> bool:
    execution = executions.get(inventory["receipt_id"])
    return bool(
        execution
        and execution["binding"]["status"] == "verified"
        and execution["material_status"] == "available"
        and execution["receipt"]["status"] == "passed"
        and inventory.get("resource_manifest_artifact_id") is not None
        and inventory["compilation_database_artifact_id"] is not None
        and row["status"] == "analyzed"
        and row["error_count"] == 0
        and row["context_match"] == "matched"
        and row["file"] in {
            value["path"] for value in execution["binding"]["input_artifacts"]
        }
    )


def _aggregate(values: list[Fraction], aggregation: str) -> list[Fraction]:
    if aggregation == "each":
        return values
    if aggregation in {"max", "maximum"}:
        return [max(values)]
    if aggregation in {"min", "minimum"}:
        return [min(values)]
    total = sum(values, Fraction(0))
    return [total / len(values) if aggregation == "mean" else total]


def _decisive_partial_failure(
    values: list[Fraction], parameters: dict[str, Any]
) -> bool:
    """Preserve only breaches that additional unknown values cannot reverse."""
    if not values:
        return False
    aggregation, operator = parameters["aggregation"], parameters["operator"]
    threshold = Fraction(str(parameters["threshold"]))
    if aggregation == "each":
        return any(not _meets(value, operator, threshold) for value in values)
    if aggregation in {"max", "maximum"} and operator in {"lt", "lte"}:
        return not _meets(max(values), operator, threshold)
    if aggregation in {"min", "minimum"} and operator in {"gt", "gte"}:
        return not _meets(min(values), operator, threshold)
    # The named native profile contains nonnegative counts. An observed partial
    # sum can prove an upper-bound breach; a partial mean cannot do so.
    return bool(
        aggregation == "sum"
        and parameters["metric_version"] == "cppulse-metrics-1"
        and operator in {"lt", "lte"}
        and not _meets(sum(values, Fraction(0)), operator, threshold)
    )


def metric_threshold(
    control: dict[str, Any], bundle: Mapping[str, Any], files: set[str], requested: list[str]
) -> ExtensionResult:
    """Evaluate explicitly selected metrics per file and declared job cell.

    Complete symbol aggregation requires an observed function-count inventory;
    incomplete and conflicting measurements cannot produce a positive result.
    """
    parameters = control["parameters"]
    inventories = _documents(bundle, "analysis_inventory")
    documents = _documents(bundle, "analysis_metrics")
    executions = {
        doc["receipt"]["id"]: doc for doc in _documents(bundle, "execution_facts")
    }
    issues, observations = [], []
    identifiers: set[str] = set()
    references: set[str] = set()
    failed = False
    if not files:
        issues.append("The selected source scope is empty")
    for context in requested:
        for path in sorted(files):
            groups: list[tuple[list[Fraction], bool]] = []
            selected = [
                inventory for inventory in inventories
                if inventory["job_context_id"] == context
                and path in inventory["requested_files"]
            ]
            for inventory in selected:
                references.update(_inventory_references(inventory))
                row = next((item for item in inventory["items"] if item["file"] == path), None)
                if row is None or not _observed(inventory, row, executions):
                    continue
                rows = [
                    item for document in documents
                    if document.get("analysis_inventory_id") == inventory["id"]
                    and document.get("job_context_id") == context
                    for item in document["items"]
                    if item["file"] == path
                    and item["context_id"] == row["parse_context_id"]
                    and item["metric_version"] == parameters["metric_version"]
                ]
                candidates = [
                    item for item in rows
                    if item["metric"] == parameters["metric"]
                    and item["units"] == parameters["units"]
                    and (item["symbol"] is None) == (parameters["level"] == "file")
                ]
                counts = [
                    item for item in rows
                    if parameters["level"] == "symbol"
                    and item["metric"] == "function_count"
                    and item["units"] == "functions" and item["symbol"] is None
                ]
                identifiers.update(item["id"] for item in candidates + counts)
                cells: dict[str | None, set[Fraction | None]] = {}
                for item in candidates:
                    value = Fraction(str(item["value"])) if item["availability"] == "available" else None
                    cells.setdefault(item["symbol"], set()).add(value)
                # Identical repeats do not double count. A contradictory cell is
                # unknown rather than whichever value was listed first.
                values = [next(iter(value)) for value in cells.values() if len(value) == 1 and None not in value]
                complete = bool(candidates) and len(values) == len(cells)
                if parameters["level"] == "symbol":
                    expected = {
                        item["value"] for item in counts if item["availability"] == "available"
                    }
                    complete &= len(expected) == 1 and len(cells) == next(iter(expected), None)
                else:
                    complete &= len(cells) == 1
                groups.append((values, complete))
            if not groups:
                issues.append(f"Missing observed metric cells: {path} in job {context}")
                continue
            signatures = {(tuple(sorted(values)), complete) for values, complete in groups}
            if len(signatures) != 1:
                issues.append(f"Conflicting metric inventories: {path} in job {context}")
                continue
            values, complete = groups[0]
            if not complete:
                issues.append(f"Missing, conflicting or unavailable metric/symbol inventory: {path} in job {context}")
                failed |= _decisive_partial_failure(values, parameters)
                continue
            aggregated = _aggregate(values, parameters["aggregation"])
            breach = any(not _meets(value, parameters["operator"], Fraction(str(parameters["threshold"]))) for value in aggregated)
            failed |= breach
            observations.append(
                f"{path} in job {context}: {parameters['aggregation']} values "
                f"{', '.join(str(value) for value in aggregated)} {parameters['units']} "
                f"{'violates' if breach else 'meets'} {parameters['operator']} {parameters['threshold']}"
            )
    references.update(f"metric:{identifier}" for identifier in identifiers)
    return ExtensionResult(
        "failed" if failed else "unknown" if issues else "passed",
        bool(issues),
        "Numeric metric thresholds apply separately to every selected file/declared-job cell; no cross-file or cross-job pooling. " + "; ".join(observations + issues),
        (), tuple(sorted(references)), tuple(sorted(identifiers)),
    )


def reviewed_evidence(
    control: dict[str, Any], bundle: Mapping[str, Any], files: set[str], requested: list[str], now: datetime
) -> ExtensionResult:
    """Count current scoped declared review decisions, with explicit identity limits."""
    parameters = control["parameters"]
    source_digest = bundle["run_manifest"]["source"]["digest"]
    evidence = {record["id"]: record for doc in _documents(bundle, "evidence") for record in doc["records"]}
    allowed = set(parameters["reviewer_ids"])
    artifacts = set(parameters["required_artifact_ids"])
    records = [evidence[key] for key in parameters["evidence_ids"] if key in evidence]
    issues = [f"Expected review evidence is missing: {key}" for key in parameters["evidence_ids"] if key not in evidence]
    eligible = []
    for record in records:
        details = record.get("review_details")
        usable = bool(
            record["kind"] == "review" and record["origin"] == "attestation"
            and record["receipt_id"] is None and record["usability"] == "usable"
            and record["status"] in {"passed", "failed"}
            and record.get("reviewer") in allowed and details
            and details["source_digest"] == source_digest
            and details["identity_assurance"] == "self_declared"
            and _date(details["reviewed_at"]) <= now
            and _date(details["recorded_at"]) <= now
            and _date(record["expires_at"]) > now
            and artifacts <= set(details["reviewed_artifact_ids"])
            and record["context_id"] in requested
            and files & set(record["scope"]["files"])
        )
        if usable:
            eligible.append(record)
        else:
            issues.append(f"Review metadata, source, time, artifacts, declared reviewer or selected scope is unavailable: {record['id']}")
    rejected: set[str] = set()
    if not files:
        issues.append("The selected source scope is empty")
    for context in requested:
        for path in sorted(files):
            decisions = [record for record in eligible if record["context_id"] == context and path in record["scope"]["files"]]
            declared = {record["reviewer"] for record in decisions}
            if len(declared) < parameters["minimum_reviewers"]:
                issues.append(f"Insufficient distinct declared reviewer IDs: {path} in job {context}; {len(declared)}/{parameters['minimum_reviewers']}")
            rejected.update(record["id"] for record in decisions if record["status"] == "failed")
    references = {
        reference for record in records for reference in (
            f"review:{record['id']}",
            *[f"artifact:{identifier}" for identifier in record["artifact_ids"]],
        )
    }
    reason = "Declared review decisions count distinct configured reviewer IDs; they do not authenticate people or establish independent review. "
    reason += f"Declared rejection(s): {', '.join(sorted(rejected))}. " if rejected else "No current scoped declared rejection was supplied. "
    return ExtensionResult(
        "failed" if rejected else "unknown" if issues else "passed",
        bool(issues), reason + "; ".join(issues),
        tuple(sorted(record["id"] for record in records)), tuple(sorted(references)),
    )
