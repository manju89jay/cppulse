"""Replay immutable original work-unit material without a live source checkout.

This bridge retains declared scope separately from executions. Missing units have
no invented receipt, metrics, context, or zero. Hash-identified SDK inventories
are not promoted into retained SDK bytes or dependency closure.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any, Iterator

from cppulse import __version__
from cppulse.contracts import validate
from cppulse.contracts.work_unit_analysis import validate_analysis_scope
from cppulse.errors import ContractError, IntegrityError
from cppulse.identities import context_identity, digest_json
from cppulse.run_store import (
    MaterialReader,
    RunSnapshot,
    RunStore,
    StagedReadProjection,
    StagedRun,
)
from cppulse.work_units import _check


@dataclass(frozen=True)
class BoundWorkUnit:
    """Original unit facts and retained input bytes, without inferred execution."""

    request: dict[str, Any]
    result: dict[str, Any]
    inputs: dict[str, bytes]
    report: dict[str, Any] | None
    report_artifact_id: str | None = None


@dataclass(frozen=True)
class WorkUnitAnalysis:
    """Full declared scope plus the subset with genuine retained executions."""

    scope: dict[str, Any]
    units: tuple[BoundWorkUnit, ...]


def _unique(
    rows: list[dict[str, Any]], key: str, label: str
) -> dict[str, dict[str, Any]]:
    mapped = {row[key]: row for row in rows}
    if len(mapped) != len(rows):
        raise IntegrityError("Duplicate " + label)
    return mapped


def _read(
    snapshot: MaterialReader,
    identifier: str,
    kind: str,
    artifact_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if artifact_index is None:
        artifact_index = {row["id"]: row for row in snapshot.manifest["artifacts"]}
    descriptor = artifact_index.get(identifier)
    if descriptor is None or descriptor["size_bytes"] > 64 * 1024**2:
        raise IntegrityError(
            "Bounded analysis control metadata exceeds its 64 MiB limit"
        )
    try:
        document = json.loads(snapshot.read_bytes(identifier))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError("Invalid retained " + kind) from exc
    _check(kind, document)
    return document


def _retained_json(content: bytes, label: str) -> Any:
    try:
        document = json.loads(content)
        digest_json(document)
        return document
    except (ValueError, UnicodeError, RecursionError, TypeError) as exc:
        raise ContractError("Invalid retained work-unit " + label) from exc


def _invocation(
    request: dict[str, Any], receipt: dict[str, Any], inputs: dict[str, bytes]
) -> None:
    # Reconstruct argv from retained data only. The ordinary runtime helper reads
    # a live resource_manifest path and therefore cannot be used for replay.
    work = PurePosixPath(request["work_root"])
    argv = [
        receipt["argv"][0],
        "--repo",
        request["source_root"],
        "--output",
        str(work / "output"),
        "--file-list",
        str(work / request["inputs"]["selection"]["path"]),
        "--config",
        str(work / request["inputs"]["configuration"]["path"]),
        "--execution-limits-report",
        str(work / "limits.json"),
        "--file-size-bytes",
        str(request["limits"]["max_artifact_bytes"]),
    ]
    if request["inputs"]["compilation_database"] is not None:
        argv += [
            "--compilation-database",
            str(work / request["inputs"]["compilation_database"]["path"]),
        ]
    if request["inputs"]["resource_manifest"] is not None:
        resource = _retained_json(inputs["resource_manifest"], "resource inventory")
        _check("resource_inputs", resource)
        argv += ["--resource-dir", resource["root"]]
    for field, flag in (
        ("address_space_bytes", "--address-space-bytes"),
        ("cpu_seconds", "--cpu-seconds"),
    ):
        if request["limits"][field] is not None:
            argv += [flag, str(request["limits"][field])]
    invocation = context_identity(
        {
            "compiler": request["native"],
            "argv": argv,
            "working_directory": request.get("process_working_directory", str(work)),
            "language_standard": None,
            "target": None,
            "provenance": "observed",
            "dependencies": [],
            "limitations": [
                "Invocation identity is separate from native-observed parse context."
            ],
        }
    )
    if (
        receipt["argv"] != argv
        or receipt["context_id"] != invocation["id"]
        or receipt["cwd"] != invocation["working_directory"]
    ):
        raise IntegrityError("Original receipt disagrees with retained invocation")


def read_work_unit_analysis(
    snapshot: MaterialReader,
    *,
    max_input_bytes: int = 256 * 1024**2,
    max_report_bytes: int = 256 * 1024**2,
) -> WorkUnitAnalysis:
    """Bind published requests/results and preserve every declared scope row.

    Reads only immutable publication bytes. This establishes local consistency,
    not producer authentication or a complete preprocessing dependency graph.
    """
    return _read_work_unit_analysis(
        snapshot, max_input_bytes=max_input_bytes, max_report_bytes=max_report_bytes
    )


def _read_work_unit_analysis(
    snapshot: MaterialReader,
    *,
    max_input_bytes: int = 256 * 1024**2,
    max_report_bytes: int = 256 * 1024**2,
    eager_reports: bool = True,
) -> WorkUnitAnalysis:
    """Retain public replay semantics; private normalization defers report bodies."""
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 1
        for value in (max_input_bytes, max_report_bytes)
    ):
        raise ContractError("Retained bridge byte limits must be positive integers")
    snapshot.verify()
    manifest = snapshot.manifest
    artifacts = _unique(manifest["artifacts"], "id", "published artifact")
    plan = _read(snapshot, "analysis-plan", "analysis_execution_plan", artifacts)
    summary = _read(
        snapshot, "analysis-summary", "analysis_execution_summary", artifacts
    )
    bindings = _read(
        snapshot, "analysis-bindings", "analysis_execution_bindings", artifacts
    )
    source = manifest["source"]
    validate("source", plan["source"])
    declared = _unique(plan["units"], "unit_id", "declared unit")
    sources = _unique(source["files"], "path", "source file")
    if plan["source"] != source or sorted(
        row["primary_file"] for row in declared.values()
    ) != sorted(sources):
        raise IntegrityError(
            "Declared units differ from complete selected source inventory"
        )
    if (
        summary["plan_sha256"] != digest_json(plan)
        or summary["source_digest"] != source["digest"]
        or bindings["source_digest"] != source["digest"]
        or summary["unit_count"] != len(declared)
    ):
        raise IntegrityError(
            "Published execution metadata differs from declared source/plan"
        )
    links = _unique(bindings["units"], "unit_id", "unit binding")
    pins = _unique(summary["results"], "unit_id", "result pin")
    rejected = _unique(summary.get("rejected_units", []), "unit_id", "rejected unit")
    if (
        set(links) != set(pins)
        or not set(links) <= declared.keys()
        or not set(rejected) <= declared.keys()
        or set(links) & set(rejected)
    ):
        raise IntegrityError("Accepted/rejected execution ownership is inconsistent")
    rows, units = [], []
    input_cache: dict[str, bytes] = {}
    input_bytes, report_bytes = 0, 0
    for descriptor in sorted(declared.values(), key=lambda row: row["primary_file"]):
        unit_id = descriptor["unit_id"]
        row = {
            "unit_id": unit_id,
            "primary_file": descriptor["primary_file"],
            "outcome": "not_attempted",
            "parse_status": None,
            "execution": None,
            "reason": "No original accepted execution was retained.",
        }
        if unit_id not in links:
            if unit_id in rejected:
                row.update(outcome="invalid_output", reason=rejected[unit_id]["reason"])
            rows.append(row)
            continue
        link = links[unit_id]
        request = _read(
            snapshot, link["request_artifact_id"], "work_request", artifacts
        )
        result = _read(snapshot, link["result_artifact_id"], "work_result", artifacts)
        request_sha = digest_json(request)
        if (
            digest_json(result) != pins[unit_id]["sha256"]
            or result["request_sha256"] != request_sha
            or request["unit_id"] != unit_id
            or result["unit_id"] != unit_id
        ):
            raise IntegrityError(
                "Original request/result differs from frozen execution pin"
            )
        if (
            request["source_digest"] != source["digest"]
            or request["primary_file"] != descriptor["primary_file"]
            or request["primary_sha256"]
            != sources[descriptor["primary_file"]]["sha256"]
            or request["native"]["sha256"] != plan["native_sha256"]
            or request["source_root"] != plan["source_root"]
        ):
            raise IntegrityError(
                "Original request differs from global declared source/native identity"
            )
        receipt = snapshot.read_json(link["receipt_artifact_id"])
        validate("execution_receipt", receipt)
        if (
            result["execution_receipt"] != receipt
            or receipt["id"] != "native-" + request_sha
            or receipt["source_digest"] != source["digest"]
            or receipt["producer"]
            != {"name": "cppulse.execution", "version": __version__}
        ):
            raise IntegrityError(
                "Published receipt is not the original request-bound receipt"
            )
        expected_roles = {
            role: record
            for role, record in request["inputs"].items()
            if record is not None
        }
        if set(expected_roles) != set(link["inputs"]):
            raise IntegrityError("Published input role mapping is incomplete")
        inputs = {}
        for role, record in expected_roles.items():
            published = artifacts.get(link["inputs"][role])
            if published is None:
                raise IntegrityError(
                    "Retained input role does not resolve to an artifact"
                )
            if any(
                published[key] != record[key]
                for key in ("sha256", "size_bytes", "media_type")
            ):
                raise IntegrityError(
                    "Retained input bytes differ from original request"
                )
            if published["id"] not in input_cache:
                input_bytes += published["size_bytes"]
                if input_bytes > max_input_bytes:
                    raise IntegrityError(
                        "Retained unique work-unit inputs exceed the bridge byte budget"
                    )
                input_cache[published["id"]] = snapshot.read_bytes(published["id"])
            inputs[role] = input_cache[published["id"]]
        primary = inputs.get("primary_content")
        expected_primary = sources[descriptor["primary_file"]]
        if primary is None or (hashlib.sha256(primary).hexdigest(), len(primary)) != (
            expected_primary["sha256"],
            expected_primary["size_bytes"],
        ):
            raise IntegrityError("Retained primary bytes differ from declared source")
        selected = _retained_json(inputs["selection"], "selection")
        if selected != [descriptor["primary_file"]]:
            raise IntegrityError("Retained file selection differs from declared unit")
        source_manifest = _retained_json(inputs["source_manifest"], "source inventory")
        validate("source", source_manifest)
        if source_manifest["files"] != [expected_primary]:
            raise IntegrityError(
                "Per-unit source inventory differs from global selected source"
            )
        if (
            digest_json(_retained_json(inputs["configuration"], "configuration"))
            != plan["configuration_sha256"]
        ):
            raise IntegrityError("Retained configuration differs from execution plan")
        database = inputs.get("compilation_database")
        if (
            digest_json(_retained_json(database, "compilation database"))
            if database is not None
            else None
        ) != plan["compilation_database_sha256"]:
            raise IntegrityError(
                "Retained compilation database differs from execution plan"
            )
        resource = inputs.get("resource_manifest")
        resource_document = (
            _retained_json(resource, "resource inventory")
            if resource is not None
            else None
        )
        if resource_document is not None:
            _check("resource_inputs", resource_document)
            validate("source", resource_document["source"])
        if (
            resource_document["source"]["digest"]
            if resource_document is not None
            else None
        ) != plan.get("resource_inputs_sha256"):
            raise IntegrityError(
                "Retained resource inventory differs from execution plan"
            )
        validate("context", request["context"])
        original_outputs = _unique(result["artifacts"], "id", "result artifact")
        if set(link["outputs"]) != set(original_outputs):
            raise IntegrityError("Published outputs differ from original result")
        for identifier, record in original_outputs.items():
            if identifier not in artifacts or any(
                artifacts[identifier][key] != record[key]
                for key in ("sha256", "size_bytes", "media_type")
            ):
                raise IntegrityError(
                    "Retained output bytes differ from original result"
                )
        if receipt["artifact_ids"] != [
            r["id"]
            for r in result["artifacts"]
            if r["media_type"] == "application/json"
        ] or receipt["log_artifact_ids"] != [
            request["artifact_prefix"] + ".stdout",
            request["artifact_prefix"] + ".stderr",
        ]:
            raise IntegrityError(
                "Original receipt artifact namespace differs from result"
            )
        _invocation(request, receipt, inputs)
        reports = [
            r for r in result["artifacts"] if r["path"] == "output/findings.json"
        ]
        report = None
        if len(reports) == 1:
            report_bytes += reports[0]["size_bytes"]
            if report_bytes > max_report_bytes:
                raise IntegrityError(
                    "Retained work-unit native reports exceed the bridge byte budget"
                )
            if eager_reports:
                report = _retained_json(
                    snapshot.read_bytes(reports[0]["id"]), "native report"
                )
                validate("findings", report, version="prototype_v1")
        row.update(
            outcome=result["outcome"],
            parse_status=result["parse_status"],
            reason=result["reason"],
            execution={
                "request_artifact_id": link["request_artifact_id"],
                "request_sha256": request_sha,
                "result_artifact_id": link["result_artifact_id"],
                "result_sha256": pins[unit_id]["sha256"],
                "receipt_artifact_id": link["receipt_artifact_id"],
                "receipt_id": receipt["id"],
                "invocation_context_id": receipt["context_id"],
                "declared_context_id": request["context"]["id"],
            },
        )
        rows.append(row)
        units.append(
            BoundWorkUnit(
                deepcopy(request),
                deepcopy(result),
                inputs,
                report,
                reports[0]["id"] if len(reports) == 1 else None,
            )
        )
    scope = {
        "version": "1.0.0",
        "source_digest": source["digest"],
        "plan_sha256": digest_json(plan),
        "summary_sha256": digest_json(summary),
        "bindings_sha256": digest_json(bindings),
        "input_verification": (
            summary["input_verification"]
            if manifest.get("input_verification") == "verified"
            else "unavailable"
        ),
        "inventory_complete": source["inventory_complete"]
        and not plan["discovery_gaps"],
        "discovery_gaps": deepcopy(plan["discovery_gaps"]),
        "units": rows,
        "limitations": [
            "Full declared scope is separate from per-unit actual receipts; absent units have no invented execution or metric zero.",
            "Retained hashes are local consistency evidence, not authentication or closed preprocessing dependencies.",
            "Resource manifest hashes do not constitute retained SDK bytes.",
        ],
    }
    validate_analysis_scope(scope)
    return WorkUnitAnalysis(scope, tuple(units))


@dataclass(frozen=True)
class NormalizedWorkUnitAnalysis:
    """Normalized actual units and their independently retained full scope."""

    scope: dict[str, Any]
    job_context: dict[str, Any]
    analyses: tuple[Any, ...]
    bindings: tuple[dict[str, Any], ...]
    registries: tuple[dict[str, Any], ...]


@contextmanager
def _open_unit_report(
    snapshot: MaterialReader,
    artifact_id: str,
    directory: Path,
) -> Iterator[dict[str, Any]]:
    """Hold one checked original body and private projection only until use ends."""
    from cppulse.contracts.json_projection import ProjectionLimits
    from cppulse.contracts.json_stream import JsonStreamLimits
    from cppulse.native_report_reader import open_native_report
    from cppulse.streamed_native_metrics import validate_streamed_native_metrics

    descriptor = next(
        row for row in snapshot.manifest["artifacts"] if row["id"] == artifact_id
    )
    if isinstance(snapshot, RunSnapshot):
        guard = snapshot._check_manifest
    elif isinstance(snapshot, StagedReadProjection):
        guard = snapshot._assert_active
    else:
        # Custom MaterialReader implementations must supply the same liveness
        # guarantee through their public verification operation.
        guard = snapshot.verify
    with snapshot.open_binary(artifact_id) as stream:
        with open_native_report(
            stream,
            expected_sha256=descriptor["sha256"],
            expected_size=descriptor["size_bytes"],
            directory=directory,
            source_guard=guard,
            projection_limits=ProjectionLimits(
                json_limits=JsonStreamLimits(
                    max_bytes=256 * 1024**2,
                    max_item_bytes=16 * 1024**2,
                    max_array_items=10_000_000,
                )
            ),
        ) as reader:
            report = reader.document
            header = report["metadata"].get("analysis", {}).get("native_metrics")
            validate_streamed_native_metrics(
                reader.iter_analysis_files(),
                reader.iter_metric_files(),
                metrics_header=(
                    {key: value for key, value in header.items() if key != "files"}
                    if header is not None
                    else None
                ),
                directory=directory,
            )
            yield report


def normalize_work_unit_analysis(
    snapshot: MaterialReader,
) -> NormalizedWorkUnitAnalysis:
    """Normalize genuine unit facts while keeping undeclared dependencies unknown."""
    with tempfile.TemporaryDirectory(prefix="cppulse-work-unit-report-") as directory:
        return _normalize_work_unit_analysis(snapshot, directory=Path(directory))


def _normalize_work_unit_analysis(
    snapshot: MaterialReader,
    *,
    directory: Path,
) -> NormalizedWorkUnitAnalysis:
    """Normalize bounded raw payloads; final typed outputs retain original scope."""
    from collections import Counter
    from cppulse.analysis import (
        NormalizedAnalysis,
        _PRODUCER,
        _absolute,
        _id,
        _physical_loc,
        _relative,
        _include_binding,
        _settings,
        _database,
        _normalize_metrics,
    )
    from cppulse.indexed_duplication import indexed_duplicate_token_counts
    from cppulse.sdk_inputs import load_used_sdk_proof, read_used_sdk_buffers
    from cppulse.tooling import load_rule_registry

    replay = _read_work_unit_analysis(snapshot, eager_reports=False)
    sdk_proof = load_used_sdk_proof(snapshot)
    plan = _read(snapshot, "analysis-plan", "analysis_execution_plan")
    raw_links = _read(snapshot, "analysis-bindings", "analysis_execution_bindings")
    links = {row["unit_id"]: row for row in raw_links["units"]}
    source = snapshot.manifest["source"]
    sources = {row["path"]: row for row in source["files"]}
    retained = {
        unit.request["primary_file"]: unit.inputs["primary_content"]
        for unit in replay.units
    }
    unit_by_file = {unit.request["primary_file"]: unit for unit in replay.units}

    def content(path: str) -> bytes:
        if path not in retained:
            raise IntegrityError(
                "Requested project bytes were not retained by an actual unit"
            )
        return retained[path]

    job = context_identity(
        {
            "compiler": {
                "name": "cppulse.bounded-analysis-declaration",
                "version": "1.0.0",
            },
            "argv": [],
            "working_directory": plan["source_root"],
            "language_standard": None,
            "target": None,
            "provenance": "inferred",
            "dependencies": [
                {
                    "id": "native-binary",
                    "sha256": plan["native_sha256"],
                    "availability": "available",
                },
                {
                    "id": "analysis-configuration",
                    "sha256": plan["configuration_sha256"],
                    "availability": "available",
                },
                {
                    "id": "compilation-database",
                    "sha256": plan["compilation_database_sha256"],
                    "availability": (
                        "available"
                        if plan["compilation_database_sha256"]
                        else "unavailable"
                    ),
                },
                {
                    "id": "builtin-resources",
                    "sha256": plan.get("resource_inputs_sha256"),
                    "availability": (
                        "available"
                        if plan.get("resource_inputs_sha256")
                        else "unavailable"
                    ),
                },
            ],
            "limitations": [
                "Declared global analysis grouping; actual invocation and observed parse contexts remain separate."
            ],
        }
    )
    scope = {
        **deepcopy(replay.scope),
        "version": "2.0.0",
        "id": _id("scope:" + digest_json([replay.scope, job["id"]])),
        "job_context_id": job["id"],
    }
    validate("analysis_scope", scope)

    def streams() -> Iterator[tuple[str, dict[str, Any]]]:
        for row in scope["units"]:
            # Excluded declared peers still supply their unavailable original
            # frame (or missing-report sentinel), so global counts stay unknown.
            path = row["primary_file"]
            unit = unit_by_file.get(path)
            if unit is None or unit.report_artifact_id is None:
                yield path, {"availability": "unavailable", "complete": False}
                continue
            with _open_unit_report(
                snapshot, unit.report_artifact_id, directory
            ) as report:
                metrics = (
                    report["metadata"]
                    .get("analysis", {})
                    .get("native_metrics", {})
                    .get("files", [])
                )
                yield path, (
                    metrics[0]["token_stream"]
                    if len(metrics) == 1
                    else {"availability": "unavailable", "complete": False}
                )

    # Observe every original peer before indexing, so a late missing/partial
    # peer cannot exhaust a database building counts that must all be unknown.
    # The index independently checks this declaration against the full second
    # pass at EOF; neither pass invents a complete peer or a zero.
    scope_complete = True
    with closing(streams()) as peers:
        for _, stream in peers:
            if not stream.get("complete") or stream.get("availability") != "measured":
                scope_complete = False
    stream = None
    with closing(streams()) as peers:
        duplication = indexed_duplicate_token_counts(
            peers, directory=directory, scope_complete=scope_complete
        )
    analyses, bound, registries = [], [], {}
    for unit in replay.units:
        if unit.report_artifact_id is None:
            continue
        with _open_unit_report(snapshot, unit.report_artifact_id, directory) as report:
            request, result = unit.request, unit.result
            path = request["primary_file"]
            root = request["source_root"]
            receipt = result["execution_receipt"]
            link = links[request["unit_id"]]
            registry = json.loads(unit.inputs["rule_registry"])
            validate("rule_registry", registry)
            if registry != load_rule_registry():
                raise ContractError(
                    "Retained registry differs from supported current native rules"
                )
            registries[digest_json(registry)] = registry
            rules = {row["id"]: row for row in registry["rules"]}
            settings = _settings(unit.inputs["configuration"], registry)
            analysis = report["metadata"]["analysis"]
            if _absolute(report["metadata"]["repo_path"], root) != root:
                raise ContractError("Native report refers to another repository")
            coverage = analysis["files"]
            if (
                len(coverage) != 1
                or _relative(coverage[0]["path"], root, base=root) != path
            ):
                raise ContractError(
                    "Per-unit native report does not cover its actual selected file"
                )
            observed = coverage[0]
            enabled = analysis["enabled_rules"]
            expected_enabled = {
                identifier
                for identifier, rule in rules.items()
                if settings.get("rules", {})
                .get(identifier, {})
                .get(
                    "enabled",
                    rule["configuration_schema"]
                    .get("properties", {})
                    .get("enabled", {})
                    .get("default", True),
                )
            }
            if set(enabled) != expected_enabled:
                raise ContractError(
                    "Native enabled rules disagree with retained configuration"
                )
            findings = report["findings"]
            for finding in findings:
                if (
                    _relative(finding["file"], root, base=root) != path
                    or finding["rule_id"] not in enabled
                    or finding["category"] != rules[finding["rule_id"]]["category"]
                    or finding["line"] > _physical_loc(content(path))
                    or not finding["message"].strip()
                ):
                    raise ContractError(
                        "Native finding differs from retained file/rule/location"
                    )
            categories = Counter(finding["category"] for finding in findings)
            severities = Counter(finding["severity"] for finding in findings)
            if report["summary"] != {
                "total_findings": len(findings),
                "by_category": {
                    key: categories[key]
                    for key in ["memory_safety", "modernization", "complexity", "misra"]
                },
                "by_severity": {
                    key: severities[key] for key in ["error", "warning", "info"]
                },
            }:
                raise ContractError("Native finding totals disagree with findings")
            attempted = observed["status"] in {"analyzed", "partial"}
            if report["metadata"]["file_count"] != int(attempted) or report["metadata"][
                "total_loc"
            ] != (_physical_loc(content(path)) if attempted else 0):
                raise ContractError(
                    "Native analyzed totals disagree with retained source"
                )
            native_files = analysis.get("native_metrics", {}).get("files", [])
            if native_files and (
                len(native_files) != 1
                or _relative(native_files[0]["path"], root, base=root) != path
            ):
                raise ContractError("Native metric rows differ from selected unit")
            sdk_buffers = read_used_sdk_buffers(
                snapshot,
                unit_id=request["unit_id"],
                request=request,
                result=result,
                resource_manifest_bytes=unit.inputs.get("resource_manifest"),
                report=report,
                proof=sdk_proof,
            )
            arguments, cwd = observed.get("parse_arguments"), observed.get(
                "working_directory"
            )
            parse = None
            match, coherence, limitations = "unverified", "unverified", []
            if arguments is not None and cwd is not None:
                # Only genuine actual-unit primary bytes participate; absent source
                # units and external SDK manifests never become fabricated inputs.
                facts = {p: sources[p] for p in retained}
                input_links = {
                    p: links[unit_by_file[p].request["unit_id"]]["inputs"][
                        "primary_content"
                    ]
                    for p in retained
                }
                buffer, limitations, dependencies = _include_binding(
                    native_files[0] if native_files else None,
                    arguments=arguments,
                    workspace=root,
                    repo=root,
                    sources=sources,
                    input_facts=facts,
                    input_links=input_links,
                    read_content=content,
                    external_buffers=sdk_buffers,
                )
                coherence = "verified" if buffer == "matched" else buffer
                match = buffer
                if observed["compile_context"] != "database":
                    match = "mismatched" if match == "mismatched" else "unverified"
                    limitations.append(
                        "Fallback/inferred parse is separate from an exact retained database command."
                    )
                elif (
                    "compilation_database" not in unit.inputs
                    or len(
                        _database(
                            unit.inputs["compilation_database"], root, receipt["cwd"]
                        ).get(path, [])
                    )
                    != 1
                ):
                    match = "mismatched" if match == "mismatched" else "unverified"
                    limitations.append(
                        "No single retained database command matches this selected file."
                    )
                if cwd != receipt["cwd"]:
                    match = "mismatched"
                if (
                    result["outcome"] != "complete"
                    or receipt["status"] != "passed"
                    or scope["input_verification"] != "verified"
                ):
                    match = "mismatched" if match == "mismatched" else "unverified"
                    coherence = (
                        "mismatched" if coherence == "mismatched" else "unverified"
                    )
                parse = context_identity(
                    {
                        "compiler": deepcopy(analysis["parser"]),
                        "argv": deepcopy(arguments),
                        "working_directory": cwd,
                        "language_standard": None,
                        "target": None,
                        "provenance": "observed",
                        "dependencies": dependencies
                        + [
                            {
                                "id": link["inputs"][role],
                                "sha256": request["inputs"][role]["sha256"],
                                "availability": "available",
                            }
                            for role in ["rule_registry", "configuration"]
                        ],
                        "limitations": limitations,
                    }
                )
            row = {
                "file": path,
                "parse_context_id": parse["id"] if parse else None,
                "status": observed["status"],
                "error_count": observed["error_count"],
                "context_source": observed["compile_context"] if parse else "none",
                "context_match": match,
                "buffer_coherence": coherence,
                "executed_rules": (
                    list(enabled)
                    if observed["status"] == "analyzed" and observed["error_count"] == 0
                    else []
                ),
                "finding_count": len(findings),
                "limitations": limitations,
            }
            inventory_id = _id(
                "bounded-inventory:"
                + digest_json([scope["id"], request["unit_id"], receipt["id"]])
            )
            report_id = next(
                record["id"]
                for record in result["artifacts"]
                if record["path"] == "output/findings.json"
            )
            inventory = {
                "version": "2.0.0",
                "id": inventory_id,
                "source_digest": source["digest"],
                "producer": deepcopy(_PRODUCER),
                "receipt_id": receipt["id"],
                "job_context_id": job["id"],
                "report_artifact_id": report_id,
                "registry_artifact_id": link["inputs"]["rule_registry"],
                "config_artifact_id": link["inputs"]["configuration"],
                "compilation_database_artifact_id": link["inputs"].get(
                    "compilation_database"
                ),
                "registry_sha256": request["inputs"]["rule_registry"]["sha256"],
                "requested_files": [path],
                "requested_rules": sorted(rules),
                "enabled_rules": enabled,
                "items": [row],
                "limitations": deepcopy(scope["limitations"]),
            }
            observations = []
            for index, finding in enumerate(findings):
                rule = rules[finding["rule_id"]]
                fingerprint = digest_json(
                    {
                        "version": "native-1",
                        "file": path,
                        "context": parse["digest"],
                        "rule_id": rule["id"],
                        "rule_version": rule["version"],
                        "line": finding["line"],
                        "column": finding.get("column", 1),
                        "severity": finding["severity"],
                        "message": finding["message"],
                    }
                )
                observations.append(
                    {
                        "id": _id(
                            "bounded-observation:" + inventory_id + ":" + str(index)
                        ),
                        "producer": deepcopy(_PRODUCER),
                        "rule_id": rule["id"],
                        "rule_version": rule["version"],
                        "file": path,
                        "context_id": parse["id"],
                        "line": finding["line"],
                        "column": finding.get("column", 1),
                        "severity": finding["severity"],
                        "message": finding["message"],
                        "fingerprint": fingerprint,
                        "fingerprint_version": "native-1",
                        "evidence_ids": [],
                    }
                )
            observation_document = {
                "version": "2.0.0",
                "source_digest": source["digest"],
                "analysis_inventory_id": inventory_id,
                "items": observations,
            }
            validate("analysis_inventory", inventory)
            validate("observations", observation_document)
            metrics = (
                _normalize_metrics(
                    analysis["native_metrics"],
                    inventory,
                    root,
                    root,
                    content,
                    duplication_counts=duplication,
                )
                if "native_metrics" in analysis
                else None
            )
            if metrics is not None and (
                snapshot.manifest.get("input_verification") != "verified"
                or result["outcome"] != "complete"
                or receipt["status"] != "passed"
            ):
                for metric in metrics["items"]:
                    metric.update(value=None, availability="unavailable")
                    metric["limitations"].append(
                        "Current original execution/source binding is unavailable; raw native values remain retained."
                    )
            binding = {
                "version": "2.0.0",
                "id": _id("bounded-binding:" + inventory_id),
                "source_digest": source["digest"],
                "analysis_scope_id": scope["id"],
                "analysis_inventory_id": inventory_id,
                **{
                    key: deepcopy(link[key])
                    for key in [
                        "unit_id",
                        "request_artifact_id",
                        "result_artifact_id",
                        "receipt_artifact_id",
                        "inputs",
                        "outputs",
                    ]
                },
                "request": deepcopy(request),
                "result": deepcopy(result),
            }
            if sdk_buffers:
                binding["sdk_used_inputs_artifact_id"] = "sdk-used-inputs"
            validate("work_unit_analysis_binding", binding)
            bound.append(binding)
            analyses.append(
                NormalizedAnalysis(
                    inventory, observation_document, [parse] if parse else [], metrics
                )
            )
    snapshot.verify()
    return NormalizedWorkUnitAnalysis(
        scope, job, tuple(analyses), tuple(bound), tuple(registries.values())
    )


def _normalization_documents(
    snapshot: MaterialReader,
    normalized: NormalizedWorkUnitAnalysis,
    *,
    include_health: bool,
    profile: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Build pure typed output documents before any publication decision."""
    outputs = [("analysis_scope", normalized.scope)]
    for analysis, binding in zip(normalized.analyses, normalized.bindings):
        outputs += [
            ("work_unit_analysis_binding", binding),
            ("analysis_inventory", analysis.inventory),
            ("observations", analysis.observations),
        ]
        if analysis.metrics is not None:
            outputs.append(("analysis_metrics", analysis.metrics))
    if include_health and normalized.analyses and normalized.registries:
        from cppulse.maintenance import compute_maintenance_health

        configuration = _retained_json(
            snapshot.read_bytes(normalized.bindings[0]["inputs"]["configuration"]),
            "configuration",
        )
        health = compute_maintenance_health(
            source_digest=normalized.scope["source_digest"],
            inventories=[analysis.inventory for analysis in normalized.analyses],
            metrics=[
                analysis.metrics
                for analysis in normalized.analyses
                if analysis.metrics is not None
            ],
            observations=[analysis.observations for analysis in normalized.analyses],
            registry=normalized.registries[0],
            required_context_ids=[normalized.scope["job_context_id"]],
            expected_scopes=[normalized.scope],
            profile=profile or configuration.get("profile", "default"),
        )
        if (
            normalized.scope["input_verification"] != "verified"
            and health["aggregate"]["overall"] is not None
        ):
            raise IntegrityError(
                "Unverified original execution cannot supply a numeric health score"
            )
        outputs.append(("maintenance_health", health))
    return outputs


def persist_work_unit_analysis(
    snapshot: RunSnapshot,
    *,
    workspace: "Path",
    store: "RunStore | Path",
    current_check: Any = None,
) -> RunSnapshot:
    """Publish normalized original-unit facts after rechecking current source bytes.

    This derives a new immutable run; parent receipts and all bytes are copied
    exactly. The callback verifies finite selected source content and scope, not
    dependency closure or producer authenticity.
    """
    from datetime import datetime, timezone
    from cppulse.analysis import _id, _merged_contexts
    from cppulse.analysis_execution import discover_sources
    from cppulse.errors import InputChanged
    from cppulse.identities import verify_inputs

    normalized = normalize_work_unit_analysis(snapshot)
    manifest = snapshot.manifest
    plan = _read(snapshot, "analysis-plan", "analysis_execution_plan")
    if str(Path(workspace).resolve()) != plan["source_root"]:
        raise IntegrityError(
            "Derived bounded analysis must check its original source root"
        )

    def source_check() -> None:
        errors = verify_inputs(workspace, manifest["source"])
        files, gaps = discover_sources(workspace)
        if (
            files != sorted(row["path"] for row in manifest["source"]["files"])
            or gaps != plan["discovery_gaps"]
        ):
            errors.append(
                "Current discovered source scope differs from original execution"
            )
        if errors:
            raise InputChanged("; ".join(errors))
        if current_check is not None:
            if current_check() is not None:
                raise ContractError(
                    "Current bounded input checker must return None or raise"
                )

    verified = manifest.get("input_verification") == "verified"
    if verified:
        source_check()
    runtime = store if isinstance(store, RunStore) else RunStore(store)
    with runtime.begin() as stage:
        known_documents = {
            (entry["contract"]["kind"], digest_json(snapshot.read_json(entry["id"])))
            for entry in manifest["artifacts"]
            if entry.get("contract", {}).get("version") == "2.0.0"
        }
        for entry in manifest["artifacts"]:
            copied = stage.copy_artifact(
                entry["id"],
                snapshot.path / entry["path"],
                entry["path"],
                entry["media_type"],
                contract=entry.get("contract"),
            )
            if any(copied[key] != entry[key] for key in ("sha256", "size_bytes")):
                raise IntegrityError(
                    "Parent artifact changed while deriving bounded analysis"
                )
        registry_ids = set()
        for binding in normalized.bindings:
            original_id = binding["inputs"]["rule_registry"]
            if original_id in registry_ids:
                continue
            registry_ids.add(original_id)
            entry = next(
                row for row in manifest["artifacts"] if row["id"] == original_id
            )
            identifier = _id("typed-bounded-registry:" + entry["sha256"])
            if any(row["id"] == identifier for row in manifest["artifacts"]):
                continue
            stage.copy_artifact(
                identifier,
                snapshot.path / entry["path"],
                "analysis/registries/" + identifier + ".json",
                "application/json",
                contract="rule_registry",
            )
        outputs = _normalization_documents(
            snapshot, normalized, include_health=not verified
        )
        for index, (kind, document) in enumerate(outputs):
            if (kind, digest_json(document)) in known_documents:
                continue
            identifier = _id(
                "bounded-normalized:"
                + normalized.scope["id"]
                + ":"
                + kind
                + ":"
                + str(index)
            )
            stage.write_json(
                "analysis/" + kind + "/" + identifier + ".json",
                document,
                contract=kind,
                artifact_id=identifier,
            )
        derived = deepcopy(manifest)
        derived["run_id"] = stage.run_id
        derived["contexts"] = _merged_contexts(
            manifest["contexts"],
            [
                normalized.job_context,
                *[
                    context
                    for analysis in normalized.analyses
                    for context in analysis.derived_parse_contexts
                ],
            ],
        )
        derived["artifacts"] = stage.artifacts
        derived["finished_at"] = (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        derived["versions"] = {
            **derived["versions"],
            "bounded-normalizer": "1.0.0",
            "parent-manifest-sha256": snapshot.manifest_sha256,
        }
        derived["limitations"] = list(
            dict.fromkeys([*derived["limitations"], *normalized.scope["limitations"]])
        )
        if (
            any(
                row["execution"] is None
                or row["parse_status"] not in {"analyzed", "excluded"}
                for row in normalized.scope["units"]
            )
            and derived["status"] == "completed"
        ):
            derived["status"] = "partial"
        normalization_stage = {
            "id": _id("bounded-normalization:" + normalized.scope["id"]),
            "status": "passed",
            "depends_on": [],
            "reason": "Original per-unit facts normalized with full declared scope; no new native execution was issued.",
        }
        if normalization_stage["id"] not in {row["id"] for row in derived["stages"]}:
            derived["stages"].append(normalization_stage)
        return stage.publish(derived, source_check=source_check if verified else None)


def append_work_unit_analysis(
    stage: StagedRun,
    material: StagedReadProjection,
    *,
    profile: str = "default",
) -> dict[str, Any]:
    """Append actual-unit facts and pure health to one still-unpublished run.

    No manifest pin, parent run, receipt or source identity is manufactured. The
    caller must publish this same owned stage once with a final current-input
    check; a failure after these writes leaves this material unpublished.
    """
    from datetime import datetime, timezone
    from cppulse.analysis import _id, _merged_contexts

    if not isinstance(material, StagedReadProjection) or material._owner is not stage:
        raise ContractError(
            "Atomic normalization requires this active stage's read projection"
        )
    manifest = material.manifest
    if any(
        entry.get("contract", {}).get("kind") == "analysis_scope"
        for entry in manifest["artifacts"]
    ):
        raise ContractError(
            "Atomic normalization cannot append a second analysis scope"
        )
    normalized = normalize_work_unit_analysis(material)
    outputs = _normalization_documents(
        material, normalized, include_health=True, profile=profile
    )
    entries = {entry["id"]: entry for entry in manifest["artifacts"]}
    registry_ids = set()
    for binding in normalized.bindings:
        original_id = binding["inputs"]["rule_registry"]
        if original_id in registry_ids:
            continue
        registry_ids.add(original_id)
        entry = entries[original_id]
        identifier = _id("typed-bounded-registry:" + entry["sha256"])
        retained = stage.copy_artifact(
            identifier,
            stage.path / entry["path"],
            "analysis/registries/" + identifier + ".json",
            "application/json",
            contract="rule_registry",
        )
        if any(retained[key] != entry[key] for key in ("sha256", "size_bytes")):
            raise IntegrityError(
                "Checked staged registry bytes changed during normalization"
            )
    for index, (kind, document) in enumerate(outputs):
        identifier = _id(
            "bounded-normalized:"
            + normalized.scope["id"]
            + ":"
            + kind
            + ":"
            + str(index)
        )
        stage.write_json(
            "analysis/" + kind + "/" + identifier + ".json",
            document,
            contract=kind,
            artifact_id=identifier,
        )
    final = deepcopy(manifest)
    final["contexts"] = _merged_contexts(
        manifest["contexts"],
        [
            normalized.job_context,
            *[
                context
                for analysis in normalized.analyses
                for context in analysis.derived_parse_contexts
            ],
        ],
    )
    final["artifacts"] = stage.artifacts
    final["finished_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    final["versions"] = {
        **final["versions"],
        "bounded-normalizer": "1.0.0",
        "bounded-publication": "single-stage-v1",
    }
    final["limitations"] = list(
        dict.fromkeys([*final["limitations"], *normalized.scope["limitations"]])
    )
    if final["status"] == "completed" and any(
        row["execution"] is None or row["parse_status"] not in {"analyzed", "excluded"}
        for row in normalized.scope["units"]
    ):
        final["status"] = "partial"
    final["stages"].append(
        {
            "id": _id("bounded-normalization:" + normalized.scope["id"]),
            "status": "passed",
            "depends_on": ["bounded-native-analysis"],
            "reason": "Original actual-unit facts and conservative health computed before the sole publication; no native receipt was synthesized.",
        }
    )
    return final
