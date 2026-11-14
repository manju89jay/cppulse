"""Pure scoped policy evaluation over closed, caller-supplied v2 facts.

This module does not collect evidence or inspect a project. Packaged contract
resources are code data; project files, processes, environment, network and the
wall clock are never read. The caller supplies the assessment's explicit UTC
time. Parsed/imported labels alone cannot establish usable executed evidence.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction
import math
import re
from typing import Any

from cppulse.contracts import (
    policy_gate,
    policy_scope_paths,
    validate_bundle,
    validate_deviation_request,
    validate_evaluation_policy,
)
from cppulse.errors import ContractError, UnsupportedVersion
from cppulse.identities import digest_json

_SUPPORTED = {
    "test_outcomes",
    "required_contexts",
    "finding_limit",
    "minimum_analysis_coverage",
    "minimum_coverage",
    "sanitizer_outcome",
    "metric_threshold",
    "reviewed_evidence",
}
_APPLICABLE = {"application", "library", "header-only"}
EVALUATOR_VERSION = "1.0.0"


@dataclass(frozen=True)
class _Result:
    status: str
    incomplete: bool
    reason: str
    evidence_ids: tuple[str, ...]
    references: tuple[str, ...]
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Analysis:
    inventories: list[dict[str, Any]]
    executions: dict[str, dict[str, Any]]
    observations: dict[str, list[dict[str, Any]]]
    registered_rules: set[str]


@dataclass(frozen=True)
class _Verification:
    facts: list[dict[str, Any]]
    available: list[dict[str, Any]]
    issues: list[str]
    evidence_ids: tuple[str, ...]
    references: tuple[str, ...]


def _verification(
    control: dict[str, Any],
    family: str,
    bundle: Mapping[str, Any],
    evidence: Mapping[str, dict[str, Any]],
    receipts: Mapping[str, dict[str, Any]],
    files: set[str],
    requested: list[str],
    now: datetime,
) -> _Verification:
    records = {row["id"]: row for row in _documents(bundle, family)}
    facts, available, issues = [], [], []
    evidence_ids: set[str] = set()
    references: set[str] = set()
    if not files:
        issues.append("The selected source scope is empty")
    for identifier in control["parameters"]["fact_ids"]:
        if identifier not in records:
            issues.append(f"Expected typed fact is unavailable: {identifier}")
            continue
        fact = records[identifier]
        facts.append(fact)
        references.add(f"{family}:{identifier}")
        for receipt_id in fact["proof_receipt_ids"]:
            references.add(f"receipt:{receipt_id}")
            if now < _date(receipts[receipt_id]["finished_at"]):
                raise ContractError(
                    f"Assessment generation time precedes used typed proof {receipt_id!r} finish time",
                    path="/generated_at",
                )
        tested = fact.get("test_evidence_ids", [fact.get("test_evidence_id")])
        evidence_ids.update(value for value in tested if value in evidence)
        if family == "coverage_facts":
            artifact_ids = {
                fact["report_artifact_id"],
                *[
                    row[key]
                    for row in fact["instrumentation"]
                    for key in ("object_artifact_id", "mapping_artifact_id")
                ],
                *[
                    row[key]
                    for row in fact["profiles"]
                    for key in ("artifact_id", "binary_artifact_id")
                ],
            }
            references.update(f"artifact:{value}" for value in artifact_ids)
        else:
            artifact_ids = {
                fact["binary_artifact_id"],
                *fact["diagnostic_artifact_ids"],
                *[row["artifact_id"] for row in fact["object_proofs"]],
                *[
                    value
                    for row in fact["object_proofs"]
                    for value in row["inspection_artifact_ids"]
                ],
                *[row["artifact_id"] for row in fact["linked_components"]],
                *[row["artifact_id"] for row in fact["exercise_proofs"]],
            }
            if fact["runtime_proof"] is not None:
                artifact_ids.add(fact["runtime_proof"]["inspection_artifact_id"])
            references.update(
                f"artifact:{value}" for value in artifact_ids if value is not None
            )
            references.update(
                f"diagnostic:{identifier}:{row['id']}" for row in fact["diagnostics"]
            )
        if fact["origin"] != "execution" or fact["usability"] != "usable":
            issues.append(
                f"Typed fact is an import or unavailable execution claim: {identifier}"
            )
        elif fact["context_id"] not in requested:
            issues.append(
                f"Typed fact is outside the requested job scope: {identifier}"
            )
        elif not tested or any(
            value not in evidence or _expired(evidence[value], now) for value in tested
        ):
            issues.append(
                f"Typed fact has missing or expired underlying test evidence: {identifier}"
            )
        else:
            available.append(fact)
    references.update(_references([evidence[value] for value in sorted(evidence_ids)]))
    return _Verification(
        facts, available, issues, tuple(sorted(evidence_ids)), tuple(sorted(references))
    )


def _runtime_coverage(
    control: dict[str, Any],
    bundle: Mapping[str, Any],
    evidence: Mapping[str, dict[str, Any]],
    receipts: Mapping[str, dict[str, Any]],
    files: set[str],
    requested: list[str],
    now: datetime,
) -> _Result:
    data = _verification(
        control, "coverage_facts", bundle, evidence, receipts, files, requested, now
    )
    parameters = control["parameters"]
    issues = list(data.issues)
    observations, below = [], False
    for context in requested:
        for path in sorted(files):
            groups = [
                measurement
                for fact in data.available
                if fact["context_id"] == context
                for file in fact["files"]
                if file["file"] == path
                for measurement in file["measurements"]
                if measurement["kind"] == parameters["measurement_kind"]
                and measurement["method"] == parameters["method"]
            ]
            signatures = {
                tuple(
                    sorted(
                        (unit["id"], unit["covered"], unit["total"])
                        for unit in group["units"]
                    )
                )
                for group in groups
            }
            if not groups or len(signatures) != 1 or groups[0]["total"] == 0:
                issues.append(
                    f"Missing, incompatible, zero or conflicting coverage units: {path} in job {context}"
                )
                continue
            covered, total = groups[0]["covered"], groups[0]["total"]
            low = 100 * Fraction(str(covered)) / Fraction(str(total)) < Fraction(
                str(parameters["minimum"])
            )
            below |= low
            observations.append(
                f"{path} in job {context}: {covered}/{total} {'below' if low else 'meets'} minimum {parameters['minimum']}%"
            )
    reason = (
        f"Observed {parameters['measurement_kind']} coverage ({parameters['method']}) is evaluated separately for each selected file/job; no averaging or report union. "
        + "; ".join([*observations, *issues])
    )
    return _Result(
        "failed" if below else "unknown" if issues else "passed",
        bool(issues),
        reason,
        data.evidence_ids,
        data.references,
        tuple(sorted(fact["id"] for fact in data.facts)),
    )


def _sanitizer(
    control: dict[str, Any],
    bundle: Mapping[str, Any],
    evidence: Mapping[str, dict[str, Any]],
    receipts: Mapping[str, dict[str, Any]],
    files: set[str],
    requested: list[str],
    now: datetime,
) -> _Result:
    data = _verification(
        control, "sanitizer_facts", bundle, evidence, receipts, files, requested, now
    )
    sanitizer = control["parameters"]["sanitizer"]
    matching = [fact for fact in data.available if fact["sanitizer"] == sanitizer]
    issues = list(data.issues)
    if len(matching) != len(data.available):
        issues.append("Named typed facts do not all match the selected sanitizer")
    for fact in matching:
        scope = {
            path for proof in fact["object_proofs"] for path in proof["source_files"]
        }
        if not files & scope:
            issues.append(
                f"Named sanitizer fact is outside the selected source scope: {fact['id']}"
            )
    for context in requested:
        job = [fact for fact in matching if fact["context_id"] == context]
        scope = {
            path
            for fact in job
            for proof in fact["object_proofs"]
            for path in proof["source_files"]
        }
        for path in sorted(files - scope):
            issues.append(
                f"Missing observed {sanitizer} instrumentation: {path} in job {context}"
            )
        for fact in job:
            if not fact["linked_components"] or any(
                row["instrumentation"] != "observed"
                for row in fact["linked_components"]
            ):
                issues.append(
                    f"Selected linked component instrumentation is incomplete: {fact['id']}"
                )
    failed = [
        fact["id"]
        for fact in matching
        if fact["outcome"] == "failed"
        and fact["diagnostics"]
        and files
        & {path for proof in fact["object_proofs"] for path in proof["source_files"]}
    ]
    reason = (
        f"Credible observed {sanitizer} diagnostic(s) in selected exercised binaries: {', '.join(failed)}; raw process/test success does not erase runtime diagnostics"
        if failed
        else (
            f"The selected {sanitizer} clean instrumented/executed scope is not established"
            if issues
            else f"Observed {sanitizer} instrumented selected-source/component scope and nonzero exercised binaries have no qualified diagnostic"
        )
    )
    if issues:
        reason += "; " + "; ".join(issues)
    return _Result(
        "failed" if failed else "unknown" if issues else "passed",
        bool(issues),
        reason,
        data.evidence_ids,
        data.references,
        tuple(sorted(fact["id"] for fact in data.facts)),
    )


def _analysis_data(bundle: Mapping[str, Any]) -> _Analysis:
    observations: dict[str, list[dict[str, Any]]] = {}
    for document in _documents(bundle, "observations"):
        identifier = document.get("analysis_inventory_id")
        if identifier is not None:
            observations.setdefault(identifier, []).extend(document["items"])
    return _Analysis(
        _documents(bundle, "analysis_inventory"),
        {
            document["receipt"]["id"]: document
            for document in _documents(bundle, "execution_facts")
        },
        observations,
        {
            rule["id"]
            for document in _documents(bundle, "rule_registry")
            for rule in document["rules"]
        },
    )


def _usable_analysis(data: _Analysis, inventory: dict[str, Any], path: str) -> bool:
    execution = data.executions.get(inventory["receipt_id"])
    return execution is not None and (
        execution["binding"]["status"] == "verified"
        and execution["material_status"] == "available"
        and execution["receipt"]["status"] == "passed"
        and inventory.get("resource_manifest_artifact_id") is not None
        and inventory["compilation_database_artifact_id"] is not None
        and path in {link["path"] for link in execution["binding"]["input_artifacts"]}
    )


def _analysis_references(inventories: Sequence[dict[str, Any]]) -> set[str]:
    return {
        reference
        for inventory in inventories
        for reference in (
            f"analysis_inventory:{inventory['id']}",
            f"receipt:{inventory['receipt_id']}",
            *[
                f"artifact:{inventory[key]}"
                for key in (
                    "report_artifact_id",
                    "registry_artifact_id",
                    "config_artifact_id",
                    "compilation_database_artifact_id",
                    "resource_manifest_artifact_id",
                )
                if inventory.get(key) is not None
            ],
        )
    }


def _selected_inventories(
    data: _Analysis, files: set[str], contexts: list[str]
) -> list[dict[str, Any]]:
    return [
        inventory
        for inventory in data.inventories
        if inventory["job_context_id"] in contexts
        and files & set(inventory["requested_files"])
    ]


def _findings(
    control: dict[str, Any], data: _Analysis, files: set[str], requested: list[str]
) -> _Result:
    rules = set(control["parameters"]["rule_ids"])
    inventories = _selected_inventories(data, files, requested)
    references = _analysis_references(inventories)
    issues = []
    if not files:
        issues.append("The selected source scope is empty")
    unknown_rules = rules - data.registered_rules
    if unknown_rules:
        issues.append(
            "Expected registry rules are unavailable: "
            + ", ".join(sorted(unknown_rules))
        )
    for context in requested:
        for path in sorted(files):
            considered = any(
                inventory["job_context_id"] == context
                and _usable_analysis(data, inventory, path)
                and rules <= set(inventory["requested_rules"])
                and any(
                    row["file"] == path
                    and row["status"] == "analyzed"
                    and row["error_count"] == 0
                    and row["context_match"] == "matched"
                    and rules <= set(row["executed_rules"])
                    for row in inventory["items"]
                )
                for inventory in inventories
            )
            if not considered:
                issues.append(
                    f"Missing complete requested-rule consideration: {path} in job {context}"
                )
    counted: set[str] = set()
    evidence_ids: set[str] = set()
    for inventory in inventories:
        rows = {row["file"]: row for row in inventory["items"]}
        for observation in data.observations.get(inventory["id"], []):
            path = observation["file"]
            if path not in files or observation["rule_id"] not in rules:
                continue
            references.add(f"observation:{observation['id']}")
            evidence_ids.update(observation["evidence_ids"])
            row = rows[path]
            if (
                _usable_analysis(data, inventory, path)
                and row["status"] in {"analyzed", "partial"}
                and row["context_match"] == "matched"
            ):
                counted.add(observation["id"])
    limit = control["parameters"]["max_findings"]
    status = "failed" if len(counted) > limit else "unknown" if issues else "passed"
    reason = f"Matched selected-job observations: {len(counted)} finding(s); permitted maximum: {limit}"
    if issues:
        reason += "; " + "; ".join(issues)
    return _Result(
        status,
        bool(issues),
        reason,
        tuple(sorted(evidence_ids)),
        tuple(sorted(references)),
    )


def _parse_coverage(
    control: dict[str, Any], data: _Analysis, files: set[str], requested: list[str]
) -> _Result:
    inventories = _selected_inventories(data, files, requested)
    covered = known = 0
    for context in requested:
        for path in files:
            rows = [
                row
                for inventory in inventories
                if inventory["job_context_id"] == context
                and _usable_analysis(data, inventory, path)
                for row in inventory["items"]
                if row["file"] == path
                and (
                    row["status"] in {"skipped", "excluded"}
                    or row["context_match"] in {"matched", "mismatched"}
                )
            ]
            known += bool(rows)
            covered += any(
                row["status"] == "analyzed"
                and row["error_count"] == 0
                and row["context_match"] == "matched"
                for row in rows
            )
    denominator = len(files) * len(requested)
    unknown = denominator - known
    minimum = Fraction(str(control["parameters"]["minimum"]))
    lower = Fraction(100 * covered, denominator) if denominator else None
    upper = Fraction(100 * (covered + unknown), denominator) if denominator else None
    status = (
        "unknown"
        if denominator == 0
        else (
            "failed"
            if upper < minimum
            else "unknown" if unknown else "passed" if lower >= minimum else "failed"
        )
    )
    reason = (
        f"Analysis parse coverage: {covered}/{denominator} matched error-free parse cells; "
        f"minimum {control['parameters']['minimum']}%; {unknown} unknown cell(s). "
        "This is an operational/scope requirement, not a source defect or detector/runtime coverage"
    )
    return _Result(
        status,
        denominator == 0 or bool(unknown),
        reason,
        (),
        tuple(sorted(_analysis_references(inventories))),
    )


def _analysis_presence(
    data: _Analysis, files: set[str], requested: list[str]
) -> tuple[dict[str, set[str]], set[str]]:
    coverage = {context: set() for context in requested}
    inventories = _selected_inventories(data, files, requested)
    for inventory in inventories:
        for row in inventory["items"]:
            if (
                row["file"] in files
                and _usable_analysis(data, inventory, row["file"])
                and row["status"] in {"analyzed", "partial", "failed"}
                and row["context_match"] == "matched"
            ):
                coverage[inventory["job_context_id"]].add(row["file"])
    return coverage, _analysis_references(inventories)


def _utc_time(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|\+00:00|-00:00)",
        value,
    ):
        raise ContractError("generated_at must be an explicit RFC3339 UTC time")
    try:
        parsed = _date(value)
    except ValueError as error:
        raise ContractError("generated_at is not a valid UTC time") from error
    if parsed.utcoffset() != timedelta(0):
        raise ContractError("generated_at must use UTC")
    return parsed


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))


def _documents(bundle: Mapping[str, Any], kind: str) -> list[dict[str, Any]]:
    value = bundle.get(kind, [])
    return value if isinstance(value, list) else [value]


def _references(records: Sequence[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                reference
                for record in records
                for reference in (
                    *[
                        f"artifact:{identifier}"
                        for identifier in record["artifact_ids"]
                    ],
                    *(
                        [f"receipt:{record['receipt_id']}"]
                        if record["receipt_id"]
                        else []
                    ),
                )
            }
        )
    )


def _eligible(
    record: dict[str, Any],
    contexts: set[str],
    files: set[str],
    receipts: Mapping[str, dict[str, Any]],
    kinds: set[str],
    now: datetime,
) -> bool:
    return (
        record["context_id"] in contexts
        and bool(files & set(record["scope"]["files"]))
        and record["origin"] == "execution"
        and record["usability"] == "usable"
        and record["kind"] in kinds
        and record["status"] in {"passed", "failed"}
        and not _expired(record, now)
        and record["receipt_id"] in receipts
        and receipts[record["receipt_id"]]["status"] in {"passed", "failed"}
    )


def _expired(record: dict[str, Any], now: datetime) -> bool:
    return "expires_at" in record and _date(record["expires_at"]) <= now


def _coverage_issues(
    files: set[str],
    requested: list[str],
    records: Sequence[dict[str, Any]],
    manifest: dict[str, Any],
    extra_scope: Mapping[str, set[str]] | None = None,
) -> list[str]:
    issues = []
    declared = {context["id"] for context in manifest["contexts"]}
    if not files:
        issues.append("The selected source scope is empty")
    for context in requested:
        if context not in declared:
            issues.append(f"Expected job context is missing: {context}")
        covered = {
            path
            for record in records
            if record["context_id"] == context
            for path in record["scope"]["files"]
        }
        covered.update((extra_scope or {}).get(context, set()))
        missing = sorted(files - covered)
        if missing:
            issues.append(
                f"Missing observed scope in job {context}: {', '.join(missing)}"
            )
    return issues


def _tests(
    control: dict[str, Any],
    evidence: Mapping[str, dict[str, Any]],
    receipts: Mapping[str, dict[str, Any]],
    manifest: dict[str, Any],
    files: set[str],
    requested: list[str],
    now: datetime,
) -> _Result:
    identifiers = control["parameters"]["evidence_ids"]
    records = [
        evidence[identifier] for identifier in identifiers if identifier in evidence
    ]
    selected = [
        record
        for record in records
        if _eligible(record, set(requested), files, receipts, {"tests"}, now)
    ]
    selected_ids = {record["id"] for record in selected}
    issues = [
        f"Expected test evidence is missing or unusable: {identifier}"
        for identifier in identifiers
        if identifier not in selected_ids
    ]
    expired = [record["id"] for record in records if _expired(record, now)]
    if expired:
        issues.append(f"Expired evidence is unavailable: {', '.join(expired)}")
    failed = []
    for record in selected:
        counts = receipts[record["receipt_id"]].get("tests")
        if not counts or not counts["total"] or counts["errors"]:
            issues.append(
                f"Test counts are missing, empty or contain operational errors: {record['id']}"
            )
        if record["status"] == "failed":
            if counts and counts["failed"] > 0:
                failed.append(record["id"])
            else:
                issues.append(
                    f"Process/report failure label without failed test cases is operationally inconsistent: {record['id']}"
                )
    issues.extend(_coverage_issues(files, requested, selected, manifest))
    status = "failed" if failed else "unknown" if issues else "passed"
    reason = (
        f"Reported usable test outcomes failed: {', '.join(failed)}"
        if failed
        else "Observed named tests cover the selected files in every requested job"
    )
    if issues:
        reason += "; " + "; ".join(issues)
    return _Result(
        status,
        bool(issues),
        reason,
        tuple(record["id"] for record in records),
        _references(records),
    )


def _contexts(
    evidence: Mapping[str, dict[str, Any]],
    receipts: Mapping[str, dict[str, Any]],
    manifest: dict[str, Any],
    files: set[str],
    requested: list[str],
    now: datetime,
    analysis: _Analysis,
) -> _Result:
    records = [
        record
        for record in evidence.values()
        if record["context_id"] in requested
        and record["kind"] in {"build", "tests"}
        and bool(files & set(record["scope"]["files"]))
    ]
    eligible = [
        record
        for record in records
        if _eligible(record, set(requested), files, receipts, {"build", "tests"}, now)
    ]
    analysis_scope, analysis_references = _analysis_presence(analysis, files, requested)
    issues = _coverage_issues(files, requested, eligible, manifest, analysis_scope)
    expired = [record["id"] for record in records if _expired(record, now)]
    if issues and expired:
        issues.append(f"Expired evidence is unavailable: {', '.join(expired)}")
    referenced = records if issues else eligible
    return _Result(
        "unknown" if issues else "passed",
        bool(issues),
        (
            "; ".join(issues)
            if issues
            else "Usable observed job results cover each requested context; this does not assert those results passed"
        ),
        tuple(sorted(record["id"] for record in referenced)),
        tuple(sorted(set(_references(referenced)) | analysis_references)),
    )


def _approval_results(
    requests: Sequence[Mapping[str, Any]],
    policy: dict[str, Any],
    controls: list[dict[str, Any]],
    source_digest: str,
    now: datetime,
) -> list[dict[str, Any]]:
    declared = {control["id"]: control for control in policy["controls"]}
    observed = {control["id"]: control for control in controls}
    results = []
    identifiers: set[str] = set()
    for request in requests:
        item = deepcopy(dict(request))
        validate_deviation_request(item)
        if item["id"] in identifiers:
            raise ContractError("Duplicate deviation request ID", code="DUPLICATE_ID")
        identifiers.add(item["id"])
        if item["control_id"] not in observed:
            raise ContractError(
                "Deviation refers to an unknown control", code="UNRESOLVED_REFERENCE"
            )
        if "gate" in item and item["gate"] != "required_controls":
            raise UnsupportedVersion(
                "Only the named required_controls gate permits deviation requests"
            )
        control = observed[item["control_id"]]
        reason = None
        if item.get("gate") != "required_controls":
            reason = "Approval does not explicitly name the required_controls gate"
        elif not declared[item["control_id"]].get("allow_deviation", False):
            reason = "Policy does not permit deviations for this control"
        elif item["source_digest"] != source_digest:
            reason = "Approval source identity differs from the assessed source"
        elif not control["context_ids"] or set(item["context_ids"]) != set(
            control["context_ids"]
        ):
            reason = "Approval must cover the exact nonempty control job scope"
        elif control["status"] != "failed":
            reason = "Only a failed control can receive a required-controls exception"
        elif control["incomplete"]:
            reason = "Incomplete failures cannot be excepted"
        elif _date(item["approved_at"]) > now:
            reason = "Approval time is in the future"
        elif _date(item["expires_at"]) <= now:
            reason = "Approval has expired at assessment time"
        item["active"] = reason is None
        item["inactive_reason"] = reason
        results.append(item)
    return results


def _mass(value: Fraction) -> int | float:
    # Whole-number masses need not fit an IEEE float to remain valid JSON.
    if value.denominator == 1:
        return value.numerator
    try:
        rendered = float(value)
    except OverflowError as error:
        raise ContractError(
            "Aggregate fractional policy mass exceeds finite numeric output limits"
        ) from error
    if not math.isfinite(rendered):
        raise ContractError("Aggregate fractional policy mass must remain finite")
    return rendered


def _scores(
    controls: list[dict[str, Any]]
) -> tuple[dict[str, int | float], dict[str, float | None]]:
    totals = dict.fromkeys(("passed", "failed", "unknown"), Fraction(0))
    for control in controls:
        if control["status"] in totals:
            totals[control["status"]] += Fraction(str(control["weight"]))
    weights = {key: _mass(value) for key, value in totals.items()}
    passed, failed, unknown = (totals[key] for key in ("passed", "failed", "unknown"))
    denominator, observed = passed + failed + unknown, passed + failed
    scores = {
        "readiness": float(100 * passed / denominator) if denominator else None,
        "evidence_completeness": (
            float(100 * observed / denominator) if denominator else None
        ),
        "observed_satisfaction": float(100 * passed / observed) if observed else None,
        "maximum_possible_readiness": (
            float(100 * (passed + unknown) / denominator) if denominator else None
        ),
    }
    return weights, scores


def evaluate_policy(
    policy: dict[str, Any],
    documents: Mapping[str, dict[str, Any] | list[dict[str, Any]]],
    *,
    generated_at: str,
    deviations: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Assess supplied current-source facts without collecting or upgrading them.

    Args:
        policy: Explicit versioned policy; its full canonical digest is retained.
        documents: Closed v2 bundle with one run_manifest and supplied facts.
            Missing policy-expected evidence is unknown; dangling actual facts
            and incompatible identities are contract errors.
        generated_at: Explicit RFC3339 UTC assessment time; no implicit clock.
        deviations: Approval claims; active flags are always recomputed.

    Returns:
        A validated assessment preserving raw outcomes, weights and scores.

    Raises:
        ContractError: Invalid facts, configuration, approvals or UTC time.
        UnsupportedVersion: A predicate or requested gate has no implementation.
    """
    policy = deepcopy(policy)
    validate_evaluation_policy(policy)
    evaluator_version = policy.get("evaluator_profile", EVALUATOR_VERSION)
    for control in policy["controls"]:
        if control["kind"] not in _SUPPORTED:
            raise UnsupportedVersion(
                f"Predicate {control['kind']!r} has no gated implementation in evaluator profile {evaluator_version}"
            )
    now = _utc_time(generated_at)
    bundle = deepcopy(dict(documents))
    if "policy" in bundle and bundle["policy"] != policy:
        raise ContractError(
            "Supplied bundle policy differs from the selected policy",
            code="SUBJECT_MISMATCH",
        )
    bundle["policy"] = policy
    validate_bundle(bundle)
    manifest = bundle["run_manifest"]
    if now < _date(manifest["finished_at"]):
        raise ContractError(
            "Assessment generation time precedes the selected run's finish time",
            path="/generated_at",
        )
    source = manifest["source"]
    files = set(
        policy_scope_paths(policy, [entry["path"] for entry in source["files"]])
    )
    evidence = {
        record["id"]: record
        for document in _documents(bundle, "evidence")
        for record in document["records"]
    }
    receipts = {
        document["id"]: document for document in _documents(bundle, "execution_receipt")
    }
    analysis = _analysis_data(bundle)
    for inventory in analysis.inventories:
        if inventory["job_context_id"] in policy["contexts"] and now < _date(
            receipts[inventory["receipt_id"]]["finished_at"]
        ):
            raise ContractError(
                "Assessment generation time precedes used analysis receipt finish time",
                path="/generated_at",
            )
    declared = {control["id"]: control for control in policy["controls"]}
    reverse: dict[str, list[str]] = {identifier: [] for identifier in declared}
    degree = {
        identifier: len(control["depends_on"])
        for identifier, control in declared.items()
    }
    for identifier, control in declared.items():
        for prerequisite in control["depends_on"]:
            reverse[prerequisite].append(identifier)
    ready = deque(identifier for identifier in declared if not degree[identifier])
    evaluated: dict[str, dict[str, Any]] = {}
    while ready:
        identifier = ready.popleft()
        control = declared[identifier]
        requested = control["parameters"].get("contexts", policy["contexts"])
        if source["kind"] not in control.get("applicable_to", _APPLICABLE):
            result = _Result(
                "not_applicable",
                False,
                "The policy explicitly excludes this subject kind",
                (),
                (),
            )
        else:
            if control["kind"] == "test_outcomes":
                result = _tests(
                    control, evidence, receipts, manifest, files, requested, now
                )
            elif control["kind"] == "required_contexts":
                result = _contexts(
                    evidence, receipts, manifest, files, requested, now, analysis
                )
            elif control["kind"] == "finding_limit":
                result = _findings(control, analysis, files, requested)
            elif control["kind"] == "minimum_coverage":
                result = _runtime_coverage(
                    control, bundle, evidence, receipts, files, requested, now
                )
            elif control["kind"] == "sanitizer_outcome":
                result = _sanitizer(
                    control, bundle, evidence, receipts, files, requested, now
                )
            elif control["kind"] == "metric_threshold":
                from cppulse.policy_extensions import metric_threshold

                result = metric_threshold(control, bundle, files, requested)
            elif control["kind"] == "reviewed_evidence":
                from cppulse.policy_extensions import reviewed_evidence

                result = reviewed_evidence(control, bundle, files, requested, now)
            else:
                result = _parse_coverage(control, analysis, files, requested)
            for evidence_id in result.evidence_ids:
                receipt_id = evidence[evidence_id]["receipt_id"]
                if receipt_id in receipts and now < _date(
                    receipts[receipt_id]["finished_at"]
                ):
                    raise ContractError(
                        f"Assessment generation time precedes used receipt {receipt_id!r} finish time",
                        path="/generated_at",
                    )
            if manifest.get("input_verification", "unverified") != "verified":
                result = _Result(
                    "unknown",
                    True,
                    f"Source binding is unverified; raw reported outcome {result.status} is retained as a claim, not a current result. {result.reason}",
                    result.evidence_ids,
                    result.references,
                    result.fact_ids,
                )
            prerequisites = [evaluated[key] for key in control["depends_on"]]
            blocked = any(
                item["status"] in {"failed", "unknown"} or item["incomplete"]
                for item in prerequisites
            )
            incomplete = any(
                item["status"] == "unknown" or item["incomplete"]
                for item in prerequisites
            )
            if blocked or incomplete:
                result = _Result(
                    "unknown" if result.status == "passed" else result.status,
                    result.incomplete or incomplete or result.status == "passed",
                    result.reason
                    + "; Prerequisite controls did not establish a positive result",
                    result.evidence_ids,
                    result.references,
                    result.fact_ids,
                )
        evaluated[identifier] = {
            "id": identifier,
            "title": control["title"],
            "status": result.status,
            "reason": result.reason,
            "weight": control["weight"],
            "required": control["required"],
            "evidence_ids": list(result.evidence_ids),
            "references": list(result.references),
            "context_ids": list(requested),
            "incomplete": result.incomplete,
        }
        if control["kind"] in {"minimum_coverage", "sanitizer_outcome", "metric_threshold"}:
            evaluated[identifier]["fact_ids"] = list(result.fact_ids)
        for dependent in reverse[identifier]:
            degree[dependent] -= 1
            if not degree[dependent]:
                ready.append(dependent)
    controls = [evaluated[control["id"]] for control in policy["controls"]]
    approvals = _approval_results(deviations, policy, controls, source["digest"], now)
    weights, scores = _scores(controls)
    assessment = {
        "version": "2.0.0",
        "evaluator": {"name": "cppulse.policy", "version": evaluator_version},
        "run_id": manifest["run_id"],
        "source_digest": source["digest"],
        "policy": {
            "id": policy["id"],
            "policy_version": policy["policy_version"],
            "sha256": digest_json(policy),
        },
        "gate": policy_gate(
            policy,
            controls,
            source_scope_empty=not files,
            excepted_control_ids=[
                item["control_id"] for item in approvals if item["active"]
            ],
        ),
        "generated_at": generated_at,
        "weights": weights,
        "scores": scores,
        "controls": controls,
        "deviations": approvals,
        "limitations": [
            "Assessment covers only the supplied selected source inventory and explicit policy job contexts; it is not certification or a safety assurance.",
            "Analysis parse coverage and selected-rule consideration are distinct; experimental rules and reported test outcomes do not establish runtime coverage or standards conformity.",
        ],
    }
    if evaluator_version in {"1.1.0", "1.2.0"}:
        assessment["limitations"].append(
            "Typed runtime coverage and sanitizer outcomes describe finite selected units, instrumented components and exercised workloads; they do not establish all-access/path coverage, loaded-runtime authenticity or absence of defects."
        )
    if evaluator_version == "1.2.0":
        assessment["limitations"].append(
            "Review decisions and quorums count self-declared configured identifiers, not authenticated people or proof of independent review; numeric thresholds cover only supplied observed metric/file/job cells."
        )
    validate_bundle({**bundle, "assessment": assessment})
    return assessment
