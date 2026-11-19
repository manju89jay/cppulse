"""Bounded native orchestration with finite source scope and original receipts.

Workers check their selected primary inputs; this coordinator guards the complete
source inventory before and after execution. Retained raw compilation databases
are native inputs, not guessed libclang argument lists. Compatibility aggregation
never creates a new native execution receipt.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time
import threading
import stat
from typing import Any
from uuid import uuid4

from cppulse.config import EffectiveConfig
from cppulse.contracts import validate
from cppulse.errors import ContractError, IntegrityError
from cppulse.execution import CancellationToken
from cppulse.identities import (
    context_identity,
    digest_json,
    hash_artifact,
    snapshot_inputs,
    verify_inputs,
)
from cppulse.native import NativeInstallation
from cppulse.tooling import load_rule_registry
from cppulse.work_units import (
    _check,
    _invocation,
    _read_json,
    _roots,
    _write,
    execute_work_units,
    prepare_work_unit,
    validate_work_unit,
    _verify_artifact,
    _observed_context,
    _resource_files,
    _validate_receipt_identity,
)

_EXTENSIONS = {
    ".cpp",
    ".cc",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".ipp",
    ".inl",
    ".tpp",
}


@dataclass(frozen=True)
class AnalysisExecution:
    """One checked bounded attempt, including partial and cancelled unit facts."""

    work_root: Path
    report_path: Path
    summary_path: Path
    source: dict[str, Any]
    contexts: list[dict[str, Any]]
    results: list[tuple[dict[str, Any], dict[str, Any]]]
    summary: dict[str, Any]
    persistent_work: bool
    plan: dict[str, Any]
    source_observations: dict[str, Any]
    rejected: list[tuple[dict[str, Any], str]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def discover_sources(root: Path) -> tuple[list[str], list[str]]:
    """Discover native-supported regular C++ files; retain traversal gaps."""
    paths: list[str] = []
    gaps: list[str] = []

    def error(exc: OSError) -> None:
        gaps.append(f"Unreadable discovery location: {exc.filename}")

    for directory, directories, files in os.walk(
        root, followlinks=False, onerror=error
    ):
        parent = Path(directory)
        for name in list(directories):
            if (parent / name).is_symlink():
                directories.remove(name)
                gaps.append(
                    f"Symlink directory not traversed: {(parent / name).relative_to(root).as_posix()}"
                )
        for name in files:
            path = parent / name
            if path.suffix.lower() not in _EXTENSIONS:
                continue
            if path.is_symlink() or not path.is_file():
                gaps.append(
                    f"Nonregular source not analyzed: {path.relative_to(root).as_posix()}"
                )
                continue
            paths.append(path.relative_to(root).as_posix())
    return sorted(paths), sorted(gaps)


def observe_source_inputs(root: Path, paths: list[str]) -> list[dict[str, Any]]:
    """Record separate filesystem observations without changing content identity.

    File and parent-directory ctime/mtime/inode changes conservatively expose
    transient edits/restores and selected include-namespace changes. These are
    observations, not an immutable filesystem or authentication guarantee.
    """
    selected = {"."}
    for relative in paths:
        selected.add(relative)
        parent = Path(relative).parent
        while str(parent) != ".":
            selected.add(parent.as_posix())
            parent = parent.parent
    records = []
    for relative in sorted(selected):
        try:
            info = (root / relative).lstat()
            records.append(
                {
                    "path": relative,
                    "kind": "directory" if stat.S_ISDIR(info.st_mode) else "file",
                    "device": info.st_dev,
                    "inode": info.st_ino,
                    "mode": info.st_mode,
                    "size_bytes": (
                        info.st_size if not stat.S_ISDIR(info.st_mode) else None
                    ),
                    "mtime_ns": info.st_mtime_ns,
                    "ctime_ns": info.st_ctime_ns,
                }
            )
        except OSError:
            records.append({"path": relative, "kind": "unavailable"})
    return records


def _database(
    config: EffectiveConfig, limit: int
) -> tuple[list[dict[str, Any]] | None, str | None]:
    selected = config.compilation_database
    if selected is None:
        selected = next(
            (
                path
                for path in (
                    config.repo / "compile_commands.json",
                    config.repo / "build/compile_commands.json",
                )
                if path.is_file()
            ),
            None,
        )
    if selected is None:
        return None, None
    if selected.is_dir():
        selected = selected / "compile_commands.json"
    document = _read_json(selected, limit)
    if not isinstance(document, list) or not document:
        raise ContractError("Selected compilation database must contain commands")
    for row in document:
        if isinstance(row, dict) and any(
            "\0" in value
            for key in ("directory", "file", "command")
            if isinstance((value := row.get(key)), str)
        ):
            raise ContractError("Compilation database strings cannot contain NUL")
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("directory"), str)
            or not Path(row["directory"]).is_absolute()
            or not isinstance(row.get("file"), str)
            or not row["file"]
        ):
            raise ContractError(
                "Bounded compilation commands require an absolute directory and source file"
            )
        arguments = row.get("arguments")
        if arguments is not None:
            if (
                not isinstance(arguments, list)
                or not arguments
                or any(
                    not isinstance(value, str) or not value or "\0" in value
                    for value in arguments
                )
            ):
                raise ContractError(
                    "Compilation database arguments must be explicit nonempty strings"
                )
        elif not isinstance(row.get("command"), str) or not row["command"]:
            raise ContractError("Compilation database command is missing")
    return document, digest_json(document)


def _declared_context(
    root: Path,
    relative: str,
    database: list[dict[str, Any]] | None,
    database_digest: str | None,
) -> dict[str, Any]:
    if database is None:
        return context_identity(
            {
                "compiler": {"name": "libclang", "version": "observed-by-native"},
                "argv": ["-std=c++17", "-x", "c++"],
                "working_directory": str(root),
                "language_standard": "c++17",
                "target": None,
                "provenance": "fallback",
                "dependencies": [],
                "limitations": [
                    "No recorded compilation command; native fallback C++17 context."
                ],
            }
        )
    exact = [
        row
        for row in database
        if (Path(row["directory"]) / row["file"]).resolve() == root / relative
    ]
    row = exact[0] if exact else None
    argv = row.get("arguments", [row.get("command", "")]) if row else []
    return context_identity(
        {
            "compiler": {
                "name": argv[0] if argv else "retained-compilation-database",
                "version": "unexecuted-declaration",
            },
            "argv": argv,
            "working_directory": row["directory"] if row else str(root),
            "language_standard": None,
            "target": None,
            "provenance": "observed" if row else "inferred",
            "dependencies": [
                {
                    "id": "compilation-database",
                    "sha256": database_digest,
                    "availability": "available",
                }
            ],
            "limitations": [
                "Raw compiler declaration is retained without executing a compiler. Actual libclang parse arguments remain separately observed.",
                "Native first-command/header interpolation semantics are preserved; this does not qualify every additional build configuration.",
            ],
        }
    )


def validate_execution_plan(plan: dict[str, Any]) -> None:
    """Validate plan shape, finite full scope, unique ownership and root boundaries."""
    _check("analysis_execution_plan", plan)
    validate("source", plan["source"])
    _roots(plan["source_root"], plan["work_root"])
    if not math.isfinite(plan["execution"]["wall_seconds"]):
        raise ContractError("Unit wall budget must be finite")
    paths = [row["primary_file"] for row in plan["units"]]
    if paths != sorted(row["path"] for row in plan["source"]["files"]) or len(
        {row["unit_id"] for row in plan["units"]}
    ) != len(paths):
        raise ContractError(
            "Execution units must own the complete selected inventory once"
        )


def _unavailable(
    relative: str,
    root: Path,
    reason: str,
    *,
    status: str = "failed",
    token_limit: int = 100000,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = str(root / relative)
    inventory = {
        "path": path,
        "status": status,
        "compile_context": "none",
        "error_count": 0,
        "parse_arguments": None,
        "working_directory": None,
        "reason": reason,
    }
    metric = {
        "path": path,
        "status": status,
        "error_count": 0,
        "measurement_complete": False,
        "source_content_sha256": None,
        "physical_loc": None,
        "code_loc": None,
        "function_count": None,
        "functions": [],
        "includes": [],
        "limitations": [reason],
        "token_stream": {
            "method": "cppulse-spelled-tokens-1",
            "availability": "unavailable",
            "record_limit": token_limit,
            "complete": False,
            "total_tokens": None,
            "retained_tokens": 0,
            "records": [],
            "limitations": [reason],
        },
    }
    return inventory, metric


def _report(unit: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:
    reports = [
        row for row in result["artifacts"] if row["path"] == "output/findings.json"
    ]
    if result["outcome"] not in ("complete", "partial") or not reports:
        return None
    path = Path(unit["work_root"]) / reports[0]["path"]
    return _read_json(path, unit["limits"]["max_artifact_bytes"])


def _contains_dynamic_input_query(path: Path) -> bool:
    """Conservatively restrict qualification; absence never proves closure.

    Warm reuse is independently denied without a qualified dependency/query
    manifest. This recognizer does not implement the C++ preprocessor.
    """
    markers = (
        b"__has_include",
        b"__has_embed",
        # Clang's embed input is not reported by inclusion callbacks. Reject
        # even conservative lexical matches until those bytes are retained.
        b"embed",
        b"__DATE__",
        b"__TIME__",
        b"__TIMESTAMP__",
        b"##",
        b"%:%:",
        b"_Pragma",
        b"__pragma",
        b"??=",
        b"??/",
    )
    overlap = b""
    pending = b""
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                raw = pending + chunk
                if raw.endswith(b"\\\r"):
                    raw, pending = raw[:-2], raw[-2:]
                elif raw.endswith(b"\\"):
                    raw, pending = raw[:-1], raw[-1:]
                else:
                    pending = b""
                # Join logical preprocessing lines before looking for opaque
                # operators, preserving both logical and raw chunk boundaries.
                text = overlap + raw.replace(b"\\\r\n", b"").replace(
                    b"\\\n", b""
                ).replace(b"\\\r", b"")
                if any(marker in text for marker in markers):
                    return True
                overlap = text[-64:]
    except OSError:
        return True
    return False


def verify_include_bindings(
    results: list[tuple[dict[str, Any], dict[str, Any]]],
    source: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Bind native TU include buffers to selected/current dependency bytes.

    Missing legacy buffer identities remain unknown. Source/header buffer
    mismatches remain changed even if their on-disk bytes were restored.
    This does not declare the include/negative-query graph closed for caching.
    """
    source_files = {row["path"]: row for row in source["files"]}
    changes: set[str] = set()
    unknown: set[str] = set()
    current: dict[str, dict[str, Any] | None] = {}
    inspected_queries: set[str] = set()
    for unit, result in results:
        report = _report(unit, result)
        if report is None:
            continue
        root = Path(unit["source_root"])
        primary = unit["inputs"].get("primary_content")
        if primary is not None and _contains_dynamic_input_query(
            Path(unit["work_root"]) / primary["path"]
        ):
            unknown.add(
                "Preprocessor/time/query input closure is unqualified for "
                + unit["primary_file"]
            )
        arguments = report["metadata"]["analysis"]["files"][0]["parse_arguments"] or []
        hidden_prefixes = (
            "-include",
            "-imacros",
            "-fmodule",
            "-fmodules",
            "-ivfsoverlay",
            "-ast-merge",
            "-fpch",
            "@",
        )
        for argument in arguments:
            if argument.startswith(hidden_prefixes):
                unknown.add(
                    "Input closure is unqualified for hidden/PCH/module/overlay/response context flag: "
                    + argument
                )
        for metric in (
            report["metadata"]["analysis"].get("native_metrics", {}).get("files", [])
        ):
            for edge in metric["includes"]:
                if edge["target_kind"] == "unresolved":
                    continue
                identity = edge.get("content_identity")
                target = edge["target"]
                if not identity or identity["status"] != "available":
                    unknown.add(
                        "Native include-buffer identity is unavailable for " + target
                    )
                    continue
                path = Path(target) if Path(target).is_absolute() else root / target
                try:
                    relative = path.relative_to(root).as_posix()
                except ValueError:
                    relative = None
                expected = source_files.get(relative)
                if expected is not None and any(
                    identity[key] != expected[key] for key in ("sha256", "size_bytes")
                ):
                    changes.add(
                        "Native TU header buffer differs from selected source: "
                        + target
                    )
                physical = str(path)
                if physical not in inspected_queries:
                    if _contains_dynamic_input_query(path):
                        unknown.add(
                            "Preprocessor/time/query input closure is unqualified for dependency "
                            + target
                        )
                    inspected_queries.add(physical)
                if physical not in current:
                    try:
                        current[physical] = hash_artifact(
                            path,
                            "dependency",
                            "dependency.bin",
                            "application/octet-stream",
                        )
                    except (ContractError, IntegrityError, OSError):
                        current[physical] = None
                observed = current[physical]
                if observed is None or any(
                    identity[key] != observed[key] for key in ("sha256", "size_bytes")
                ):
                    changes.add(
                        "Native TU include buffer differs from current dependency: "
                        + target
                    )
    return sorted(changes), sorted(unknown)


def _aggregate(
    root: Path,
    work: Path,
    plan: dict[str, Any],
    results: list[tuple[dict[str, Any], dict[str, Any]]],
    *,
    input_changed: bool,
    unavailable_reasons: dict[str, str] | None = None,
) -> Path:
    """Stream compatible native output without retaining every unit token stream."""
    by_file = {unit["primary_file"]: (unit, result) for unit, result in results}
    analysis_header = None
    metric_header = None
    total_loc, file_count = 0, 0
    counts: Counter[str] = Counter()
    for unit, result in results:
        report = _report(unit, result)
        if report is None:
            continue
        header = report["metadata"]["analysis"]
        candidate = {
            key: value
            for key, value in header.items()
            if key not in ("files", "native_metrics")
        }
        metrics = header.get("native_metrics")
        if analysis_header is None:
            analysis_header = candidate
            metric_header = (
                {key: value for key, value in metrics.items() if key != "files"}
                if metrics
                else None
            )
        elif analysis_header != candidate or (
            metrics
            and metric_header
            != {key: value for key, value in metrics.items() if key != "files"}
        ):
            raise IntegrityError(
                "Unit parser/rule/metric versions differ during aggregation"
            )
        if not input_changed:
            total_loc += report["metadata"]["total_loc"]
            file_count += report["metadata"]["file_count"]
    analysis_header = analysis_header or {"enabled_rules": []}
    token_limit = metric_header["max_token_records"] if metric_header else 100000

    def rows(kind: str) -> Iterator[dict[str, Any]]:
        for descriptor in plan["units"]:
            pair = by_file.get(descriptor["primary_file"])
            report = _report(*pair) if pair else None
            if report is None or input_changed:
                reason = (
                    "Global source inputs changed; raw unit facts retained separately."
                    if input_changed
                    else (
                        pair[1]["reason"]
                        if pair
                        else (unavailable_reasons or {}).get(
                            descriptor["primary_file"],
                            "Unit was not attempted before interruption.",
                        )
                    )
                )
                inventory, metric = _unavailable(
                    descriptor["primary_file"], root, reason, token_limit=token_limit
                )
            else:
                inventory = report["metadata"]["analysis"]["files"][0]
                metric = (
                    report["metadata"]["analysis"]
                    .get("native_metrics", {})
                    .get("files", [None])[0]
                )
            yield inventory if kind == "inventory" else metric

    target = work / "findings.json"
    with target.open("w", encoding="utf-8") as stream:

        def emit(value: Any) -> None:
            stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False))

        def array(values: Iterator[Any]) -> None:
            stream.write("[")
            first = True
            for value in values:
                if not first:
                    stream.write(",")
                emit(value)
                first = False
            stream.write("]")

        stream.write('{"version":"1.0.0","metadata":')
        metadata = {
            "repo_path": str(root),
            "analyzed_at": _now(),
            "file_count": file_count,
            "total_loc": min(total_loc, 2147483647),
        }
        stream.write(json.dumps(metadata)[:-1] + ',"analysis":')
        stream.write(json.dumps(analysis_header)[:-1] + ',"files":')
        array(rows("inventory"))
        if metric_header is not None:
            stream.write(',"native_metrics":')
            stream.write(json.dumps(metric_header)[:-1] + ',"files":')
            array(rows("metrics"))
            stream.write("}")
        stream.write('}},"findings":[')
        first = True
        if not input_changed:
            for unit, result in results:
                report = _report(unit, result)
                for finding in report["findings"] if report else []:
                    if not first:
                        stream.write(",")
                    emit(finding)
                    first = False
                    counts["total"] += 1
                    counts["category:" + finding["category"]] += 1
                    counts["severity:" + finding["severity"]] += 1
        stream.write('],"summary":')
        emit(
            {
                "total_findings": counts["total"],
                "by_category": {
                    name: counts["category:" + name]
                    for name in (
                        "memory_safety",
                        "modernization",
                        "complexity",
                        "misra",
                    )
                },
                "by_severity": {
                    name: counts["severity:" + name]
                    for name in ("error", "warning", "info")
                },
            }
        )
        stream.write("}\n")
    return target


def run_analysis(
    config: EffectiveConfig,
    native: NativeInstallation,
    work_root: Path,
    *,
    timeout: float = 300,
    cancel: CancellationToken | None = None,
) -> AnalysisExecution:
    """Run the complete discovered finite scope in bounded isolated native units.

    Source edits invalidate the current global binding. Exclusions/skips stay in
    native inventory; partial/crashed/timed-out units never become clean files.
    Resume retains original successful receipts only where checked inputs permit;
    unknown include closure forces a fresh attempt for that unit.
    """
    if (
        config.execution["mode"] != "bounded"
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ContractError(
            "Bounded mode and a finite positive analysis timeout are required"
        )
    started = _now()
    began = time.monotonic()
    root, base = _roots(config.repo, config.execution["work_directory"] or work_root)
    base.mkdir(parents=True, exist_ok=True)
    paths, gaps = discover_sources(root)
    source_before = observe_source_inputs(root, paths)
    source = snapshot_inputs(root, paths, inventory_complete=not gaps)
    if source_before != observe_source_inputs(root, paths):
        raise IntegrityError(
            "Source inputs changed while establishing the initial boundary"
        )
    database, db_digest = _database(config, config.execution["output_bytes"])
    resource_snapshot = (
        snapshot_inputs(native.resource_dir, _resource_files(native.resource_dir))
        if native.resource_dir is not None
        else None
    )
    resource_digest = (
        resource_snapshot["digest"] if resource_snapshot is not None else None
    )
    native_sha = hash_artifact(
        native.analyzer, "native", "native", "application/octet-stream"
    )["sha256"]
    signature = digest_json(
        {
            "source": source["digest"],
            "config": config.settings,
            **({"ruleset_digest": config.ruleset["digest"]} if config.ruleset else {}),
            "database": db_digest,
            "native": native_sha,
            "execution": {
                key: value
                for key, value in config.execution.items()
                if key not in ("resume", "work_directory")
            },
            "resources": resource_digest,
        }
    )
    pointer = base / "latest_execution.json"
    selected = (
        _read_json(pointer, 8192)
        if config.execution["resume"] and pointer.exists()
        else None
    )
    if selected is not None and selected.get("signature") == signature:
        attempt = base / selected["attempt"]
        if not attempt.is_relative_to(base) or ".." in Path(selected["attempt"]).parts:
            raise IntegrityError("Execution checkpoint escapes selected work directory")
    else:
        attempt = base / ("attempt-" + uuid4().hex)
    _roots(root, attempt)
    attempt.mkdir(exist_ok=True)
    units = [
        {
            "unit_id": "unit-"
            + digest_json(
                {"file": path, "database": db_digest, "configuration": config.settings,
                 **({"ruleset_digest": config.ruleset["digest"]} if config.ruleset else {})}
            )[:32],
            "primary_file": path,
            "context_mode": "compilation_database" if database else "fallback",
        }
        for path in paths
    ]
    plan = {
        "version": "1.0.0",
        "source_root": str(root),
        "work_root": str(attempt),
        "source": source,
        "configuration_sha256": digest_json(config.settings),
        "native_sha256": native_sha,
        "compilation_database_sha256": db_digest,
        "resource_inputs_sha256": resource_digest,
        "execution": dict(config.execution),
        "units": units,
        "discovery_gaps": gaps,
        "limitations": [
            "Native first-command and header interpolation behavior is preserved; additional configuration qualification remains separate.",
            "Dependency closure is not established; this execution makes no positive extraction-cache claim.",
        ],
    }
    validate_execution_plan(plan)
    plan_path = attempt / "analysis-plan.json"
    if plan_path.exists():
        old = _read_json(plan_path, config.execution["output_bytes"])
        comparison = dict(plan)
        comparison["execution"] = {
            **comparison["execution"],
            "resume": old["execution"]["resume"],
        }
        if comparison != old:
            raise IntegrityError(
                "Execution checkpoint plan differs from selected inputs"
            )
        plan = old
    else:
        _write(plan_path, plan)
    _write(pointer, {"signature": signature, "attempt": attempt.name})
    shared_database = (
        attempt / "compile_commands.json" if database is not None else None
    )
    if shared_database is not None:
        if shared_database.exists():
            if (
                digest_json(
                    _read_json(shared_database, config.execution["output_bytes"])
                )
                != db_digest
            ):
                raise IntegrityError("Retained shared compilation database changed")
        else:
            _write(shared_database, database)
    token = cancel or CancellationToken()
    deadline = began + timeout
    registry = load_rule_registry()
    source_by_path = {row["path"]: row for row in source["files"]}
    previous_summary = (
        _read_json(attempt / "analysis-summary.json", config.execution["output_bytes"])
        if (attempt / "analysis-summary.json").exists()
        else None
    )
    previous_pins = (
        {row["unit_id"]: row for row in previous_summary["results"]}
        if previous_summary is not None
        else {}
    )
    prepared: dict[str, dict[str, Any]] = {}
    yielded: dict[str, bool] = {}
    environment = native.environment()
    loader_environment = {
        key: environment.get(key, "")
        for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")
    }

    def requests() -> Iterator[dict[str, Any]]:
        for descriptor in units:
            if token.is_cancelled() or time.monotonic() >= deadline:
                token.cancel()
                return
            parent = attempt / "units" / descriptor["unit_id"]
            parent.mkdir(parents=True, exist_ok=True)
            latest = parent / "latest.json"
            previous = _read_json(latest, 8192) if latest.exists() else None
            if previous is not None and (
                not isinstance(previous, dict)
                or not isinstance(previous.get("attempt"), str)
                or not previous["attempt"].startswith("attempt-")
                or Path(previous["attempt"]).name != previous["attempt"]
            ):
                raise IntegrityError("Unit checkpoint path is not a canonical attempt")
            destination = (
                parent / previous["attempt"] if previous else parent / "attempt-0000"
            )
            if previous and (destination / "result.json").exists():
                result = _read_json(destination / "result.json", 1024 * 1024)
                request = _read_json(destination / "request.json", 1024 * 1024)
                _check("work_result", result)
                pin = previous_pins.get(descriptor["unit_id"])
                if pin is not None and pin["sha256"] != digest_json(result):
                    raise IntegrityError(
                        "Resume result differs from previous execution summary"
                    )
                if result["outcome"] in ("complete", "partial"):
                    checked = validate_work_unit(
                        request, result, native_executable=native.analyzer
                    )
                    includes = any(
                        row["includes"]
                        for row in checked.report["metadata"]["analysis"]
                        .get("native_metrics", {})
                        .get("files", [])
                    )
                else:
                    includes = True
                # Empty includes do not prove closed preprocessing/query inputs.
                if (
                    includes
                    or request.get("fact_key") is None
                    or request.get("dependency_manifest") is None
                ):
                    destination = (
                        parent / f"attempt-{len(list(parent.glob('attempt-*'))):04d}"
                    )
            if (
                previous
                and not (destination / "result.json").exists()
                and destination.exists()
            ):
                destination = (
                    parent / f"attempt-{len(list(parent.glob('attempt-*'))):04d}"
                )
            one_source = {
                **source,
                "files": [source_by_path[descriptor["primary_file"]]],
                "inventory_complete": False,
            }
            projection = {
                key: one_source[key] for key in ("kind", "files", "inventory_complete")
            }
            one_source["digest"] = digest_json(projection)
            context = _declared_context(
                root, descriptor["primary_file"], database, db_digest
            )
            unit = prepare_work_unit(
                unit_id=descriptor["unit_id"],
                source_root=root,
                work_root=destination,
                source=one_source,
                primary_file=descriptor["primary_file"],
                context=context,
                native_executable=native.analyzer,
                configuration=config.settings,
                registry=registry,
                resource_directory=native.resource_dir,
                context_mode=descriptor["context_mode"],
                compilation_database=database,
                global_source_digest=source["digest"],
                environment=loader_environment,
                artifact_prefix=descriptor["unit_id"] + "." + destination.name,
                compilation_database_file=shared_database,
                retain_primary=True,
                inherit_resource_environment=False,
                process_working_directory=root,
                limits={
                    "wall_seconds": config.execution["wall_seconds"],
                    "cpu_seconds": config.execution["cpu_seconds"],
                    "address_space_bytes": config.execution["address_space_bytes"],
                    "max_artifact_bytes": config.execution["output_bytes"],
                },
            )
            prepared[descriptor["unit_id"]] = unit
            _write(latest, {"attempt": destination.name})
            yield unit

    failure = None
    interruption = "none"
    timer = threading.Timer(max(0, deadline - time.monotonic()), token.cancel)
    timer.daemon = True
    timer.start()
    try:
        for execution in execute_work_units(
            requests(),
            native_executable=native.analyzer,
            jobs=config.execution["jobs"],
            cancel=token,
            propagate_interrupt=True,
        ):
            yielded[execution.result["unit_id"]] = execution.resumed
    except KeyboardInterrupt:
        token.cancel()
        interruption = "keyboard_interrupt"
    except (ContractError, IntegrityError, OSError) as exc:
        token.cancel()
        failure = str(exc)
    finally:
        timer.cancel()
    results = []
    rejected: list[tuple[dict[str, Any], str]] = []
    links = []
    contexts: dict[str, dict[str, Any]] = {}
    for unit in prepared.values():
        result_path = Path(unit["work_root"]) / "result.json"
        if not result_path.exists():
            continue
        try:
            result = _read_json(result_path, 1024 * 1024)
            _check("work_result", result)
            pin = _read_json(Path(unit["work_root"]) / "checkpoint.json", 8192)
            _check("work_checkpoint", pin)
            if pin["request_sha256"] != digest_json(unit) or pin[
                "result_sha256"
            ] != digest_json(result):
                raise IntegrityError(
                    "Rejected checkpoint result differs from original pin"
                )
            _validate_receipt_identity(unit, result, native.analyzer)
        except (ContractError, IntegrityError, OSError) as exc:
            rejected.append((unit, str(exc)))
            failure = failure or str(exc)
            continue
        results.append((unit, result))
        relative = result_path.relative_to(attempt).as_posix()
        links.append(
            {
                "unit_id": unit["unit_id"],
                "result_path": relative,
                "sha256": hash_artifact(
                    result_path, "result", relative, "application/json"
                )["sha256"],
                "resumed": yielded.get(unit["unit_id"], False),
            }
        )
        invocation = _invocation(unit, native.analyzer.resolve())[1]
        contexts[invocation["id"]] = invocation
        contexts[unit["context"]["id"]] = unit["context"]
        report = _report(unit, result)
        for record in result["artifacts"]:
            _verify_artifact(Path(unit["work_root"]), record)
        if (
            report is not None
            and report["metadata"]["analysis"]["files"][0]["parse_arguments"]
            is not None
        ):
            observed = _observed_context(unit, report)
            contexts[observed["id"]] = observed
    after_paths, after_gaps = discover_sources(root)
    try:
        _, after_db = _database(config, config.execution["output_bytes"])
    except (ContractError, IntegrityError, OSError):
        after_db = "changed"
    change_reasons: list[str] = []
    source_after = observe_source_inputs(root, paths)
    source_observations = {
        "version": "1.0.0",
        "source_digest": source["digest"],
        "before": source_before,
        "after": source_after,
        "limitations": [
            "Filesystem observations remain separate from content/context identities; this is not an immutable filesystem guarantee."
        ],
    }
    _check("analysis_source_observations", source_observations)
    _write(attempt / "source-observations.json", source_observations)
    if source_after != source_before:
        change_reasons.append(
            "Source metadata or parent namespace changed during execution; original bytes may have been restored."
        )
    if bool(verify_inputs(root, source)) or paths != after_paths or gaps != after_gaps:
        change_reasons.append(
            "Source content or discovery inventory changed during native execution."
        )
    if after_db != db_digest:
        change_reasons.append(
            "Selected compilation database changed during native execution."
        )
    try:
        if (
            shared_database is not None
            and digest_json(
                _read_json(shared_database, config.execution["output_bytes"])
            )
            != db_digest
        ):
            change_reasons.append(
                "Retained compilation database changed during native execution."
            )
    except (ContractError, IntegrityError, OSError):
        change_reasons.append(
            "Retained compilation database became unavailable during native execution."
        )
    if native.resource_dir is not None:
        try:
            current_resources = snapshot_inputs(
                native.resource_dir, _resource_files(native.resource_dir)
            )
            if current_resources["digest"] != resource_digest:
                change_reasons.append(
                    "Selected builtin resources changed during native execution."
                )
        except (ContractError, IntegrityError, OSError):
            change_reasons.append(
                "Selected builtin resources became unavailable during native execution."
            )
    try:
        if (
            hash_artifact(
                native.analyzer, "native", "native", "application/octet-stream"
            )["sha256"]
            != native_sha
        ):
            change_reasons.append(
                "Selected native executable changed during native execution."
            )
    except (ContractError, IntegrityError, OSError):
        change_reasons.append(
            "Selected native executable became unavailable after execution."
        )
    include_changes, include_unknown = verify_include_bindings(results, source)
    change_reasons.extend(include_changes)
    changed = bool(change_reasons)
    report_path = _aggregate(
        root,
        attempt,
        plan,
        results,
        input_changed=changed,
        unavailable_reasons={unit["primary_file"]: reason for unit, reason in rejected},
    )
    outcomes = Counter(result["outcome"] for _, result in results)
    outcomes["invalid_output"] += len(rejected)
    outcomes["not_attempted"] += len(units) - len(results) - len(rejected)
    completed = sum(
        result["outcome"] == "complete" or result["parse_status"] == "excluded"
        for _, result in results
    )
    if changed:
        status = "input_changed"
    elif any(result["outcome"] == "cancelled" for _, result in results) or (
        len(results) < len(units) and failure is None and token.is_cancelled()
    ):
        status = "cancelled"
    elif (
        units
        and completed == len(units)
        and not gaps
        and failure is None
        and not include_unknown
    ):
        status = "completed"
    else:
        status = "partial"
    if interruption == "none" and status == "cancelled":
        interruption = "deadline" if time.monotonic() >= deadline else "cancellation"
    summary = {
        "version": "1.0.0",
        "interruption": interruption,
        "plan_sha256": digest_json(plan),
        "source_digest": source["digest"],
        "source_observations_sha256": digest_json(source_observations),
        "status": status,
        "input_verification": (
            "changed" if changed else "unavailable" if include_unknown else "verified"
        ),
        "unit_count": len(units),
        "completed_units": completed,
        "resumed_units": sum(row["resumed"] for row in links),
        "outcomes": dict(outcomes),
        "results": links,
        "rejected_units": [
            {"unit_id": unit["unit_id"], "reason": reason} for unit, reason in rejected
        ],
        "report_sha256": hash_artifact(
            report_path, "aggregate", "findings.json", "application/json"
        )["sha256"],
        "limitations": [
            *plan["limitations"],
            *(
                [
                    "Resume requested with unknown dependency/query closure: native units ran fresh; historical checkpoints remain retained."
                ]
                if config.execution["resume"]
                else []
            ),
            *gaps,
            *change_reasons,
            *include_unknown,
            *([failure] if failure else []),
        ],
        "started_at": started,
        "finished_at": _now(),
    }
    _check("analysis_execution_summary", summary)
    summary_path = attempt / "analysis-summary.json"
    _write(summary_path, summary)
    return AnalysisExecution(
        attempt,
        report_path,
        summary_path,
        source,
        list(contexts.values()),
        results,
        summary,
        config.execution["work_directory"] is not None,
        plan,
        source_observations,
        rejected,
    )


def index_published_execution(snapshot: Any, catalog_path: Path) -> None:
    """Rebuild finite catalog rows from checked immutable publication metadata.

    This reads no current source/compiler/work directory and issues no receipt or
    assessment. Failed/cancelled attempts are indexed with their explicit scope.
    The derived SQLite transaction is separate from immutable publication.
    """
    from cppulse.work_unit_store import WorkUnitIndex

    plan = json.loads(snapshot.read_bytes("analysis-plan"))
    summary = json.loads(snapshot.read_bytes("analysis-summary"))
    bindings = json.loads(snapshot.read_bytes("analysis-bindings"))
    _check("analysis_execution_plan", plan)
    _check("analysis_execution_summary", summary)
    _check("analysis_execution_bindings", bindings)
    if (
        digest_json(plan) != summary["plan_sha256"]
        or summary["source_digest"] != snapshot.manifest["source"]["digest"]
        or bindings["source_digest"] != summary["source_digest"]
    ):
        raise IntegrityError("Catalog inputs differ from the immutable run identity")
    result_ids = {
        row["unit_id"]: row["result_artifact_id"] for row in bindings["units"]
    }
    pins = {row["unit_id"]: row for row in summary["results"]}
    rejected = {
        row["unit_id"]: row["reason"] for row in summary.get("rejected_units", [])
    }

    def summaries() -> Iterator[dict[str, Any]]:
        for descriptor in plan["units"]:
            identifier = result_ids.get(descriptor["unit_id"])
            if identifier is None:
                reason = rejected.get(
                    descriptor["unit_id"],
                    "No accepted result was available before interruption.",
                )
                row = {
                    "unit_id": descriptor["unit_id"],
                    "primary_file": descriptor["primary_file"],
                    "outcome": (
                        "invalid_output"
                        if descriptor["unit_id"] in rejected
                        else "not_attempted"
                    ),
                    "parse_status": None,
                    "reason": reason,
                }
            else:
                result = json.loads(snapshot.read_bytes(identifier))
                _check("work_result", result)
                if (
                    descriptor["unit_id"] not in pins
                    or digest_json(result) != pins[descriptor["unit_id"]]["sha256"]
                ):
                    raise IntegrityError(
                        "Catalog result differs from original execution pin"
                    )
                row = {
                    "unit_id": descriptor["unit_id"],
                    "primary_file": descriptor["primary_file"],
                    "outcome": result["outcome"],
                    "parse_status": result["parse_status"],
                    "reason": result["reason"],
                    "request_sha256": result["request_sha256"],
                }
            row["input_verification"] = snapshot.manifest["input_verification"]
            row["execution_status"] = summary["status"]
            if len(row["reason"]) > 4096:
                row["reason"] = (
                    row["reason"][:4000] + " [truncated; see retained execution result]"
                )
            yield row

    WorkUnitIndex(catalog_path).publish(
        snapshot.run_id, snapshot.manifest_sha256, summaries()
    )


def index_execution(
    snapshot: Any, execution: AnalysisExecution, catalog_path: Path
) -> None:
    """Compatibility adapter; catalog reconstruction uses immutable bytes only."""
    if execution.source["digest"] != snapshot.manifest["source"]["digest"]:
        raise IntegrityError("Execution source differs from published run")
    index_published_execution(snapshot, catalog_path)
