"""Installed command dispatcher; project execution is always an explicit command."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib import metadata, util
import json
import logging
import os
from pathlib import Path
import platform
import signal
import stat
import subprocess
import sys
import time
from typing import Any, Iterator
import zipfile

import jsonschema

from cppulse import __version__
from cppulse.config import effective_config, initialize
from cppulse.errors import (
    ContractError,
    CppulseError,
    IntegrityError,
)


def doctor() -> dict[str, Any]:
    """Probe native startup and report detected optional packages without installs."""
    from cppulse.native import discover_native

    result: dict[str, Any] = {
        "cppulse": __version__,
        "python": platform.python_version(),
        "platform": sys.platform,
        "machine": platform.machine(),
        "optional": {},
    }
    for feature, package, module in [
        ("ml", "xgboost", "xgboost"),
        ("pdf", "weasyprint", "weasyprint"),
        ("web", "fastapi", "fastapi"),
    ]:
        try:
            result["optional"][feature] = {
                "installed": util.find_spec(module) is not None,
                "version": metadata.version(package),
                "execution_verified": False,
            }
        except metadata.PackageNotFoundError:
            result["optional"][feature] = {
                "installed": False,
                "hint": f"Install cppulse[{feature}] for this feature",
            }
    try:
        native = discover_native()
        probe = subprocess.run(
            [str(native.analyzer), "--help"],
            env=native.environment(),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        result["native"] = {
            "available": probe.returncode == 0,
            "path": str(native.analyzer),
            "metadata": str(native.metadata) if native.metadata else None,
            "resource_dir": str(native.resource_dir) if native.resource_dir else None,
            "startup_exit": probe.returncode,
            "limitations": list(native.limitations),
        }
        if probe.returncode:
            result["native"]["error"] = probe.stderr[-2000:]
    except (CppulseError, OSError, subprocess.SubprocessError) as exc:
        result["native"] = {
            "available": False,
            "error": str(exc),
            "error_code": getattr(exc, "code", type(exc).__name__),
        }
    return result


def diagnostic_bundle(output: Path) -> Path:
    """Write local summary metadata, excluding source, environment and raw paths."""
    inspection = doctor()
    report = {
        key: inspection[key]
        for key in ("cppulse", "python", "platform", "machine")
        if key in inspection
    }
    # Distribution versions may contain private local tags. Export capability
    # status rather than copying optional metadata or future doctor fields.
    report["optional"] = {
        feature: {
            key: inspection["optional"][feature][key]
            for key in ("installed", "execution_verified")
            if key in inspection["optional"][feature]
        }
        for feature in ("ml", "pdf", "web")
        if feature in inspection["optional"]
    }
    native = inspection["native"]
    report["native"] = {
        key: native[key]
        for key in ("available", "startup_exit", "error_code")
        if key in native
    }
    report["redaction"] = (
        "No source, environment, argv, paths, logs, configuration values or optional package version strings included."
    )
    report["created_at"] = datetime.now(timezone.utc).isoformat()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with (
        output.open("xb") as stream,
        zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive,
    ):
        archive.writestr("diagnostics.json", json.dumps(report, indent=2))
    return output


def _analysis_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--repo", type=Path, required=True)
    command.add_argument("--output", type=Path, default=Path("output"))
    command.add_argument("--config", type=Path)
    command.add_argument("--profile", choices=["default", "safety-critical"])
    command.add_argument("--compilation-database", type=Path)
    command.add_argument(
        "--execution",
        choices=["bounded", "legacy"],
        help="Select bounded per-file workers or the compatibility extractor",
    )
    command.add_argument("--jobs", type=int, help="Maximum active native workers")
    command.add_argument(
        "--unit-timeout",
        type=float,
        help="Wall-time budget per native work unit, in seconds",
    )
    command.add_argument(
        "--cpu-seconds", type=int, help="CPU budget per native work unit"
    )
    command.add_argument(
        "--memory-limit-mib",
        type=int,
        help="Address-space budget per native work unit, in MiB",
    )
    command.add_argument(
        "--output-limit-mib",
        type=int,
        help="Output-file budget per native work unit, in MiB",
    )
    command.add_argument(
        "--work-directory",
        type=Path,
        help="Retain checked native work state outside the analyzed repository",
    )
    command.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Resume checked retained work; requires a work directory",
    )

    command.add_argument(
        "--history",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable optional history mining or retain explicit unavailable history",
    )
    command.add_argument(
        "--history-cache", type=Path, help="Explicit reusable bounded raw-history cache"
    )
    command.add_argument(
        "--behavior-config",
        type=Path,
        help="Declared aliases, teams and behavior window JSON",
    )
    command.add_argument("--behavior-cutoff", help="Explicit aware UTC behavior cutoff")


def _history_overrides(args: argparse.Namespace) -> dict[str, Any] | None:
    """Preserve omitted flags and explicit history disabling."""
    values = {
        "enabled": args.history,
        "cache_dir": (
            str(args.history_cache) if args.history_cache is not None else None
        ),
        "behavior_config": (
            str(args.behavior_config) if args.behavior_config is not None else None
        ),
        "behavior_cutoff": args.behavior_cutoff,
    }
    return {key: value for key, value in values.items() if value is not None} or None


def _execution_overrides(args: argparse.Namespace) -> dict[str, Any] | None:
    """Translate explicit flags only, preserving project-setting precedence."""
    values = {
        "mode": args.execution,
        "jobs": args.jobs,
        "wall_seconds": args.unit_timeout,
        "cpu_seconds": args.cpu_seconds,
        "address_space_bytes": (
            None if args.memory_limit_mib is None else args.memory_limit_mib * 1024**2
        ),
        "output_bytes": (
            None if args.output_limit_mib is None else args.output_limit_mib * 1024**2
        ),
        "work_directory": (
            None if args.work_directory is None else str(args.work_directory)
        ),
        "resume": args.resume,
    }
    return {key: value for key, value in values.items() if value is not None} or None


def _run_options(command: argparse.ArgumentParser, *, workspace: bool) -> None:
    command.add_argument("--store", type=Path, required=True)
    if workspace:
        command.add_argument("--workspace", type=Path, required=True)
    command.add_argument("--run-id")
    command.add_argument("--manifest-sha256")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cppulse",
        description="Local C++ analysis and scoped verification evidence (development candidate)",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    capability = subcommands.add_parser(
        "capabilities",
        help="Print public client protocol versions without executing tools",
    )
    capability.add_argument("--format", choices=["json"], default="json")
    subcommands.add_parser(
        "doctor", help="Inspect installed capabilities; never installs dependencies"
    )
    init = subcommands.add_parser("init", help="Create editable project configuration")
    init.add_argument("--repo", type=Path, default=Path.cwd())
    config = subcommands.add_parser(
        "config", help="Print effective settings without running analysis"
    )
    _analysis_options(config)
    for name in ("analyze", "watch"):
        command = subcommands.add_parser(name)
        _analysis_options(command)
        command.add_argument(
            "--format", choices=["json", "html", "pdf"], default="html"
        )
        command.add_argument("--timeout", type=float, default=300)
        if name == "watch":
            command.add_argument("--interval", type=float, default=300)
            command.add_argument("--iterations", type=int)
    report = subcommands.add_parser("report")
    report.add_argument("--input", type=Path, default=Path("output"))
    report.add_argument("--output", type=Path)
    report.add_argument("--format", choices=["json", "html", "pdf"], default="pdf")
    report.add_argument("--evidence", action="store_true")
    report.add_argument("--run-id")
    report.add_argument("--manifest-sha256")
    report.add_argument("--assessment-artifact-id")
    capture = subcommands.add_parser(
        "collect", help="Execute an explicit finite collection request"
    )
    capture.add_argument("--request", type=Path, required=True)
    capture.add_argument("--workspace", type=Path, required=True)
    capture.add_argument("--store", type=Path, required=True)
    assess = subcommands.add_parser(
        "assess", help="Assess retained current material; execute no project commands"
    )
    _run_options(assess, workspace=True)
    assess.add_argument("--policy", type=Path, required=True)
    check = subcommands.add_parser(
        "check", help="Check current retained material without collecting or building"
    )
    _run_options(check, workspace=True)
    mode = check.add_mutually_exclusive_group(required=True)
    mode.add_argument("--policy", type=Path)
    mode.add_argument("--findings", type=Path, metavar="REQUEST")
    explain = subcommands.add_parser(
        "explain",
        help="Read the exact historical snapshot view without current-source claims",
    )
    _run_options(explain, workspace=False)
    explain.add_argument("--assessment-artifact-id")
    baseline = subcommands.add_parser(
        "baseline", help="Record an explicit scoped finding baseline"
    )
    baseline_commands = baseline.add_subparsers(dest="baseline_command", required=True)
    create = baseline_commands.add_parser("create")
    _run_options(create, workspace=True)
    create.add_argument("--request", type=Path, required=True)
    sarif = subcommands.add_parser(
        "export-sarif", help="Export checked historical observations as SARIF 2.1.0"
    )
    _run_options(sarif, workspace=False)
    sarif.add_argument("--comparison-artifact-id")
    compare = subcommands.add_parser(
        "compare",
        help="Compare checked upstream consumer scope with current local evidence",
    )
    _run_options(compare, workspace=True)
    compare.add_argument("--upstream-bundle", type=Path, required=True)
    for field in (
        "upstream-root-id",
        "upstream-manifest-sha256",
        "upstream-subject-id",
        "local-subject-id",
        "upstream-matrix-id",
        "local-matrix-id",
    ):
        compare.add_argument("--" + field, required=True)
    maintenance = subcommands.add_parser(
        "maintenance",
        help="Score retained measurements for explicitly required contexts",
    )
    _run_options(maintenance, workspace=True)
    maintenance.add_argument("--required-context", action="append", required=True)
    maintenance.add_argument("--optional-context", action="append", default=[])
    maintenance.add_argument("--allow-inferred-parse", action="store_true")
    maintenance.add_argument(
        "--profile", choices=["default", "safety-critical"], default="default"
    )
    portfolio = subcommands.add_parser(
        "portfolio", help="Read pinned projects or run one explicit local report tick"
    )
    portfolio_commands = portfolio.add_subparsers(
        dest="portfolio_command", required=True
    )
    for name in ("report", "tick"):
        command = portfolio_commands.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument(
            "--at",
            help="Explicit timezone-aware ISO replay clock; default is current UTC",
        )
        if name == "tick":
            command.add_argument(
                "--output-root",
                type=Path,
                required=True,
                help="Existing authorized directory for local report artifacts",
            )
    layout = subcommands.add_parser(
        "store-layout",
        help="Explicit store migration or separate legacy snapshot export",
    )
    layout_actions = layout.add_subparsers(dest="layout_action", required=True)
    upgrade = layout_actions.add_parser(
        "upgrade", help="Explicitly migrate a v2 store to v3"
    )
    upgrade.add_argument("--store", type=Path, required=True)
    export = layout_actions.add_parser(
        "export-v2", help="Export a separate offline v2 snapshot"
    )
    export.add_argument("--store", type=Path, required=True)
    export.add_argument("--destination", type=Path, required=True)
    recovery = subcommands.add_parser(
        "store-recovery",
        help="Inspect a writer lock or explicitly recover an exact dead local owner",
    )
    recovery_actions = recovery.add_subparsers(dest="recovery_action", required=True)
    recovery_inspect = recovery_actions.add_parser(
        "inspect", help="Read lock observations without changing the store"
    )
    recovery_inspect.add_argument("--store", type=Path, required=True)
    recovery_inspect.add_argument("--expected-lock-sha256")
    recovery_inspect.add_argument("--expected-lock-token")
    recovery_execute = recovery_actions.add_parser(
        "recover",
        help="Preserve staged bytes and quarantine only the exact selected dead-owner lock",
    )
    recovery_execute.add_argument("--store", type=Path, required=True)
    recovery_execute.add_argument("--expected-lock-sha256", required=True)
    recovery_execute.add_argument("--expected-lock-token", required=True)
    issues = subcommands.add_parser(
        "issues",
        help="Read bounded public GitHub issue observations; financial inputs remain caller claims",
    )
    issues.add_argument("--request", type=Path, required=True)
    issues.add_argument("--output", type=Path, required=True)
    branches = subcommands.add_parser(
        "branches",
        help="Read pinned local branch facts; declared deliveries are not provider verification",
    )
    for name in ("repo", "config", "output"):
        branches.add_argument("--" + name, type=Path, required=True)
    abi = subcommands.add_parser(
        "abi-compare",
        help="Retain a bounded, pinned ELF/DWARF comparison report; exit0 is report completion, not compatibility approval",
    )
    abi.add_argument("--request", type=Path, required=True)
    abi.add_argument("--output", type=Path, required=True)
    service_proposal = subcommands.add_parser(
        "verify-service-proposal",
        help="Verify an explicitly trusted, pinned finite C++ service regression in disjoint copies",
    )
    for name in ("request", "output"):
        service_proposal.add_argument("--" + name, type=Path, required=True)
    service_proposal.add_argument(
        "--execute-trusted-project", action="store_true", required=True
    )
    proposal = subcommands.add_parser(
        "verify-proposal",
        help="Verify a pinned proposal in a fresh copy of an explicitly trusted C++17 project",
    )
    for name in ("store", "workspace", "request", "output-root"):
        proposal.add_argument("--" + name, type=Path, required=True)
    proposal.add_argument(
        "--execute-trusted-project",
        action="store_true",
        required=True,
        help="Execute selected trusted CMake/CTest code in an isolated source copy",
    )
    fix = subcommands.add_parser(
        "fix",
        help="Write a source-pinned dry-run repair plan; never applies source changes",
    )
    fix.add_argument("--store", type=Path, required=True)
    fix.add_argument("--workspace", type=Path, required=True)
    fix.add_argument("--run-id", required=True)
    fix.add_argument("--manifest-sha256", required=True)
    fix.add_argument("--observation-id", action="append")
    fix.add_argument("--output", type=Path, required=True)
    diagnostics = subcommands.add_parser(
        "diagnostics", help="Create an explicitly local redacted diagnostic ZIP"
    )
    diagnostics.add_argument("--output", required=True, type=Path)
    serve = subcommands.add_parser("serve", help="Serve the optional local API")
    serve.add_argument("--input", type=Path, default=Path("output"))
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    scaffold = subcommands.add_parser(
        "scaffold", help="Create a draft extension; does not register or execute it"
    )
    scaffold.add_argument("kind", choices=["rule", "adapter", "policy"])
    scaffold.add_argument("name")
    scaffold.add_argument("--destination", type=Path, default=Path.cwd())
    return parser


def _read_request(path: Path) -> dict[str, Any]:
    """Read one bounded stable JSON object; reject duplicate keys and NaN."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ContractError("JSON contains a duplicate key: " + key)
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ContractError("Nonfinite JSON value is unsupported: " + value)

    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ContractError("Request/policy must be a regular JSON file")
            content = stream.read(64 * 1024 * 1024 + 1)
            after = os.fstat(stream.fileno())
        if len(content) > 64 * 1024 * 1024:
            raise ContractError("Request/policy exceeds the 64 MiB input bound")

        def fields(info: os.stat_result) -> tuple[int, ...]:
            return (
                info.st_dev,
                info.st_ino,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )

        if fields(before) != fields(after):
            raise ContractError("Request/policy changed while reading")
        document = json.loads(content, object_pairs_hook=pairs, parse_constant=constant)
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, CppulseError):
            raise
        raise ContractError("Cannot read selected JSON input: " + str(error)) from error
    if not isinstance(document, dict):
        raise ContractError("Request/policy JSON must contain an object")
    return document


@contextmanager
def _cancellation() -> Iterator[Any]:
    """Translate SIGINT into observed cooperative collector cancellation."""
    from cppulse.execution import CancellationToken

    token = CancellationToken()

    def cancel(signum: int, frame: Any) -> None:
        token.cancel()

    previous = None
    try:
        previous = signal.signal(signal.SIGINT, cancel)
    except ValueError:
        pass  # A library caller may run main outside the main Python thread.
    try:
        yield token
    finally:
        if previous is not None:
            signal.signal(signal.SIGINT, previous)


def _selected_run(args: argparse.Namespace) -> Any:
    from cppulse.run_store import RunStore

    reader = RunStore.open_existing(args.store)
    return (
        reader.open_run(args.run_id, manifest_sha256=args.manifest_sha256)
        if args.run_id
        else reader.resolve_latest_attempt()
    )


def _new_command(args: argparse.Namespace) -> tuple[dict[str, Any] | None, int]:
    from cppulse.contracts import validate
    from cppulse.workflows import (
        assess_run,
        check_findings,
        check_policy,
        collect_request,
        compare_runs,
        create_baseline,
        run_reference,
        workflow_result,
    )

    snapshot = None
    operation = args.command
    try:
        if operation == "collect":
            request = _read_request(args.request)
            with _cancellation() as token:
                result = collect_request(
                    request, workspace=args.workspace, store=args.store, cancel=token
                )
        else:
            # Read-only resolution freezes one run/pin before any writer exists.
            snapshot = _selected_run(args)
            if operation == "explain":
                from cppulse.presentation import build_snapshot_view

                return (
                    build_snapshot_view(
                        snapshot, assessment_artifact_id=args.assessment_artifact_id
                    ),
                    0,
                )
            if operation == "export-sarif":
                from cppulse.sarif import build_sarif

                comparison = None
                if args.comparison_artifact_id:
                    descriptor = next(
                        (
                            row
                            for row in snapshot.manifest["artifacts"]
                            if row["id"] == args.comparison_artifact_id
                        ),
                        {},
                    )
                    if (
                        descriptor.get("contract", {}).get("kind")
                        != "finding_comparison"
                    ):
                        raise ContractError(
                            "Selected SARIF comparison must be a typed finding_comparison"
                        )
                    comparison = snapshot.read_json(args.comparison_artifact_id)
                return build_sarif(snapshot, comparison=comparison), 0
            if operation == "assess":
                result = assess_run(
                    snapshot,
                    _read_request(args.policy),
                    workspace=args.workspace,
                    store=args.store,
                )
            elif operation == "baseline":
                result = create_baseline(
                    snapshot,
                    _read_request(args.request),
                    workspace=args.workspace,
                    store=args.store,
                )
            elif operation == "compare":
                result = compare_runs(
                    snapshot,
                    upstream_bundle=args.upstream_bundle,
                    upstream_root_id=args.upstream_root_id,
                    upstream_manifest_sha256=args.upstream_manifest_sha256,
                    upstream_subject_id=args.upstream_subject_id,
                    local_subject_id=args.local_subject_id,
                    upstream_matrix_id=args.upstream_matrix_id,
                    local_matrix_id=args.local_matrix_id,
                    workspace=args.workspace,
                    store=args.store,
                )
            elif args.policy is not None:
                result = check_policy(
                    snapshot,
                    _read_request(args.policy),
                    workspace=args.workspace,
                    store=args.store,
                )
            else:
                result = check_findings(
                    snapshot,
                    _read_request(args.findings),
                    workspace=args.workspace,
                    store=args.store,
                    request_root=args.findings.absolute().parent,
                )
        return result, result["exit_code"]
    except (CppulseError, OSError, RuntimeError, KeyboardInterrupt) as failure:
        if isinstance(failure, KeyboardInterrupt):
            error = CppulseError("Workflow cancelled", code="CANCELLED")
            code = 130
        else:
            error = (
                failure
                if isinstance(failure, CppulseError)
                else CppulseError(str(failure), code="IO_ERROR")
            )
            code = (
                3
                if error.code
                in {
                    "STALE_SOURCE",
                    "STALE_OUTPUT",
                    "UNVERIFIED_SOURCE",
                    "INPUT_CHANGED",
                }
                or isinstance(error, IntegrityError)
                else 2
            )
        if operation in {"explain", "export-sarif"}:
            print(json.dumps(error.as_dict()), file=sys.stderr)
            return None, code
        status = (
            "cancelled"
            if code == 130
            else (
                "invalid"
                if code == 2
                else "partial" if operation == "collect" else "insufficient_evidence"
            )
        )
        if operation == "check":
            result = {
                "version": "2.0.0",
                "mode": "policy" if args.policy is not None else "findings",
                "store": str(args.store.absolute()),
                "status": status,
                "exit_code": code,
                "reason": str(error),
                "run": run_reference(snapshot) if snapshot else None,
                "facts_base_run": None,
                "assessment_artifact_id": None,
                "comparison_artifact_id": None,
                "policy_sha256": None,
                "baseline_sha256": None,
                "error": error.as_dict(),
            }
            validate("check_result", result)
        else:
            result = workflow_result(
                operation,
                args.store,
                status=status,
                reason=str(error),
                raw=snapshot,
                error=error,
            )
            validate("workflow_result", result)
        return result, code


def main(argv: list[str] | None = None) -> int:
    """Dispatch local workflows and keep machine output separate from diagnostics."""
    parser = _parser()
    args = parser.parse_args(argv)
    if hasattr(args, "run_id") and bool(args.run_id) != bool(args.manifest_sha256):
        parser.error("--run-id and --manifest-sha256 must be supplied together")
    if hasattr(args, "store"):
        if "\\" in str(args.store) or "\0" in str(args.store):
            parser.error("--store must be a local POSIX path")
        args.store = Path(os.path.abspath(args.store))
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    exit_code = 0
    try:
        if args.command == "capabilities":
            from cppulse.client_contract import capabilities

            print(json.dumps(capabilities(), indent=2))
            return 0
        if args.command == "doctor":
            result = doctor()
            print(json.dumps(result, indent=2))
            return 0 if result["native"]["available"] else 2
        if args.command == "init":
            result = {"config": str(initialize(args.repo))}
        elif args.command == "diagnostics":
            result = {
                "diagnostics": str(diagnostic_bundle(args.output)),
                "uploaded": False,
            }
        elif args.command == "scaffold":
            from cppulse.tooling import scaffold

            result = {
                "scaffold": str(scaffold(args.kind, args.name, args.destination)),
                "registered": False,
            }
        elif args.command == "portfolio":
            from cppulse.portfolio import build_portfolio, schedule_tick

            selected = _read_request(args.config)
            now = (
                datetime.fromisoformat(args.at.replace("Z", "+00:00"))
                if args.at is not None
                else datetime.now(timezone.utc)
            )
            if args.portfolio_command == "report":
                result = build_portfolio(selected, now=now)
            else:
                result = schedule_tick(
                    selected,
                    output_root=Path(os.path.abspath(args.output_root)),
                    now=now,
                )
                exit_code = (
                    2
                    if any(
                        result["active_job_counts"][status]
                        for status in ("failed", "exhausted")
                    )
                    else 0
                )
        elif args.command == "store-layout":
            from cppulse.store_heads import export_store_v2, upgrade_store_to_v3

            if args.layout_action == "upgrade":
                result = upgrade_store_to_v3(args.store)
            else:
                result = export_store_v2(args.store, args.destination)
        elif args.command == "store-recovery":
            from cppulse.store_recovery import (
                inspect_recovery_receipt,
                inspect_store_lock,
                recover_store_lock,
            )

            if args.recovery_action == "inspect":
                if bool(args.expected_lock_sha256) != bool(args.expected_lock_token):
                    raise ContractError(
                        "Recovery inspection requires both exact lock pins"
                    )
                if args.expected_lock_sha256 is not None:
                    result = inspect_recovery_receipt(
                        args.store,
                        expected_lock_sha256=args.expected_lock_sha256,
                        expected_lock_token=args.expected_lock_token,
                    )
                else:
                    result = inspect_store_lock(args.store)
            else:
                result = recover_store_lock(
                    args.store,
                    expected_lock_sha256=args.expected_lock_sha256,
                    expected_lock_token=args.expected_lock_token,
                )
        elif args.command == "issues":
            from cppulse.issue_tracker_cli import main as issues_main

            return issues_main(
                ["--request", str(args.request), "--output", str(args.output)]
            )
        elif args.command == "branches":
            from cppulse.branch_delivery_cli import main as branches_main

            return branches_main(
                [
                    "--repo",
                    str(args.repo),
                    "--config",
                    str(args.config),
                    "--output",
                    str(args.output),
                ]
            )
        elif args.command == "abi-compare":
            from cppulse.abi import main as abi_main

            return abi_main(
                ["--request", str(args.request), "--output", str(args.output)]
            )
        elif args.command == "verify-service-proposal":
            from cppulse.service_repair import main as service_proposal_main

            return service_proposal_main(
                [
                    "--request",
                    str(args.request),
                    "--output",
                    str(args.output),
                    "--execute-trusted-project",
                ]
            )
        elif args.command == "verify-proposal":
            from cppulse.semantic_repair import main as proposal_main

            return proposal_main(
                [
                    "--store",
                    str(args.store),
                    "--workspace",
                    str(args.workspace),
                    "--request",
                    str(args.request),
                    "--output-root",
                    str(args.output_root),
                    "--execute-trusted-project",
                ]
            )
        elif args.command == "fix":
            from cppulse.repairs import main as repair_main

            command = [
                "--store",
                str(args.store),
                "--workspace",
                str(args.workspace),
                "--run-id",
                args.run_id,
                "--manifest-sha256",
                args.manifest_sha256,
                "--output",
                str(args.output),
            ]
            for observation_id in args.observation_id or []:
                command.extend(["--observation-id", observation_id])
            return repair_main(command)
        elif args.command == "maintenance":
            from cppulse.maintenance import persist_maintenance_health

            snapshot = persist_maintenance_health(
                _selected_run(args),
                workspace=args.workspace,
                store=args.store,
                required_context_ids=args.required_context,
                optional_context_ids=args.optional_context,
                allow_inferred_parse=args.allow_inferred_parse,
                profile=args.profile,
            )
            from cppulse.workflows import read_documents

            health = next(
                row
                for row in reversed(read_documents(snapshot)["maintenance_health"])
                if row["scorer"]["id"] == "analyzed-kloc-context-v4"
                and row["scorer"]["profile"] == args.profile
                and row["scorer"]["allow_inferred_parse"] == args.allow_inferred_parse
                and row["required_context_ids"] == sorted(args.required_context)
                and row["optional_context_ids"] == sorted(args.optional_context)
            )
            aggregate = health["aggregate"]
            result = {
                "run_id": snapshot.run_id,
                "manifest_sha256": snapshot.manifest_sha256,
                "maintenance": aggregate,
                "scorer": health["scorer"]["id"],
                "scorer_details": health["scorer"],
                "contexts": health["contexts"],
                "required_context_ids": health["required_context_ids"],
                "optional_context_ids": health["optional_context_ids"],
                "formula_reference": "docs/contracts/maintenance-metrics.md",
                "consumer_assurance": health["consumer_assurance"],
            }
            exit_code = 0 if aggregate["overall"] is not None else 3
        elif args.command == "serve":
            try:
                import uvicorn
            except ImportError as exc:
                raise RuntimeError(
                    "Install cppulse[web] to serve the local API"
                ) from exc
            os.environ["DATA_DIR"] = str(args.input.resolve(strict=True))
            uvicorn.run("cppulse.report_engine.api:app", host=args.host, port=args.port)
            return 0
        elif args.command in {
            "collect",
            "assess",
            "check",
            "explain",
            "baseline",
            "export-sarif",
            "compare",
        }:
            result, exit_code = _new_command(args)
            if result is not None:
                print(json.dumps(result, indent=2, allow_nan=False))
            return exit_code
        elif args.command == "report":
            from cppulse.pipeline import generate_report

            if args.evidence or args.run_id or args.assessment_artifact_id:
                result = generate_report(
                    args.input,
                    args.format,
                    args.output,
                    evidence=args.evidence,
                    run_id=args.run_id,
                    manifest_sha256=args.manifest_sha256,
                    assessment_artifact_id=args.assessment_artifact_id,
                )
            else:
                result = generate_report(args.input, args.format, args.output)
        else:
            config = effective_config(
                args.repo,
                args.output,
                config=args.config,
                profile=args.profile,
                compilation_database=args.compilation_database,
                execution=_execution_overrides(args),
                history=_history_overrides(args),
            )
            if args.command == "config":
                result = config.as_dict()
            else:
                from cppulse.pipeline import analyze

                if args.timeout <= 0 or (
                    args.command == "watch"
                    and (
                        args.interval <= 0
                        or (args.iterations is not None and args.iterations < 1)
                    )
                ):
                    parser.error(
                        "Timeout, interval and iteration count must be positive"
                    )
                count = 0
                while True:
                    result = analyze(
                        config, report_format=args.format, timeout=args.timeout
                    )
                    exit_code = 0 if result.get("analysis_status") == "completed" else 3
                    count += 1
                    if args.command != "watch" or (
                        args.iterations is not None and count >= args.iterations
                    ):
                        break
                    print(json.dumps(result), flush=True)
                    time.sleep(args.interval)
        print(json.dumps(result, indent=2))
        return exit_code
    except KeyboardInterrupt:
        print("cppulse: cancelled", file=sys.stderr)
        return 130
    except (jsonschema.ValidationError, jsonschema.SchemaError) as exc:
        print(f"cppulse: invalid contract: {exc.message}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(
            f"cppulse: missing dependency {exc.name}; reinstall cppulse with the requested feature extras",
            file=sys.stderr,
        )
        return 2
    except (CppulseError, ValueError) as exc:
        print(f"cppulse: {exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"cppulse: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
