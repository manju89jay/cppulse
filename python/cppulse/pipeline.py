"""Installed native/Python analysis, retaining compatibility output and snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, TYPE_CHECKING

from cppulse import __version__
from cppulse.compatibility import read_prototype_document
from cppulse.config import EffectiveConfig
from cppulse.errors import ContractError
from cppulse.identities import digest_json
from cppulse.importer import import_pipeline
from cppulse.native import discover_native
from cppulse.run_store import RunStore

DOCUMENTS = ("findings", "git_metrics", "risk_scores", "roadmap")
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cppulse.analysis_execution import AnalysisExecution
    from cppulse.run_store import RunSnapshot


def _failed_attempt(
    config: EffectiveConfig,
    error: BaseException,
    started: str,
    generated: Path | None = None,
) -> None:
    """Expose an operationally incomplete attempt without replacing completed data."""
    store = RunStore(config.output)
    with store.begin() as stage:
        # Failed/invalid component JSON is retained as bytes, without declaring
        # a contract it may not satisfy. A failed run is never a positive result.
        failure = stage.path / ".failure-source.json"
        failure.write_text(
            json.dumps(
                {"error_type": type(error).__name__, "message": str(error)}, indent=2
            ),
            encoding="utf-8",
        )
        stage.copy_artifact("failure", failure, "failure.json", "application/json")
        failure.unlink()
        limitations = [
            "Analysis did not complete; this attempt has no verified source inventory or current analysis results. Previous flat compatibility files may still exist; resolve latest_attempt for current state."
        ]
        if generated is not None:
            for name in (
                "analyzer.log",
                "effective_config.json",
                "settings.json",
                *[f"{name}.json" for name in DOCUMENTS],
                "report.html",
                "report.json",
                "report.pdf",
                "git_behavior.json",
                "git_history.json",
            ):
                artifact = generated / name
                if artifact.is_symlink():
                    limitations.append(
                        f"Generated diagnostic {name} was a symlink and was not retained."
                    )
                elif artifact.is_file():
                    media_type = {
                        ".json": "application/json",
                        ".pdf": "application/pdf",
                        ".html": "text/html",
                    }.get(artifact.suffix, "text/plain")
                    stage.copy_artifact(
                        name.replace(".", "-"), artifact, name, media_type
                    )
        # Failure publication must still work if the selected source directory
        # disappeared during execution. No source files are asserted here.
        empty_source = {
            "kind": "application",
            "files": [],
            "inventory_complete": False,
        }
        manifest = {
            "version": "2.0.0",
            "run_id": stage.run_id,
            "status": (
                "cancelled" if isinstance(error, KeyboardInterrupt) else "partial"
            ),
            "source": {
                "version": "2.0.0",
                "digest": digest_json(empty_source),
                **empty_source,
                "limitations": [
                    "No source inventory was collected for this failed attempt."
                ],
            },
            "contexts": [],
            "stages": [
                {
                    "id": "analysis",
                    "status": (
                        "cancelled" if isinstance(error, KeyboardInterrupt) else "error"
                    ),
                    "depends_on": [],
                    "reason": str(error) or type(error).__name__,
                }
            ],
            "artifacts": stage.artifacts,
            "started_at": started,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "config_digest": digest_json(config.as_dict()),
            "versions": {"cppulse": __version__},
            "limitations": limitations,
        }
        stage.publish(manifest)


def _legacy_analysis_completed(
    config: EffectiveConfig, snapshot: "RunSnapshot", report_name: str
) -> bool:
    """Check descriptive analysis independently of full-scope health evidence."""
    from cppulse.contracts.maintenance import BASE_CATEGORIES
    from cppulse.tooling import load_rule_registry

    metadata = snapshot.read_json("findings")["metadata"]
    # The archive importer requires an inventory and checks its in-root paths.
    coverage = metadata["analysis"]
    scope = [row for row in coverage["files"] if row["status"] != "excluded"]
    manifest = snapshot.manifest
    allowed_contexts = (
        {"database"}
        if config.compilation_database
        else {"database", "fallback", "inferred"}
    )
    categories = set(BASE_CATEGORIES)
    if config.settings["profile"] == "safety-critical":
        categories.add("misra")
    required_rules = {
        rule["id"]
        for rule in load_rule_registry()["rules"]
        if rule["category"] in categories
    }
    return (
        0 < len(scope) == metadata["file_count"] == len(manifest["source"]["files"])
        and bool(coverage.get("parser"))
        and required_rules.issubset(coverage["enabled_rules"])
        and all(
            row["status"] == "analyzed"
            and row["error_count"] == 0
            and row["compile_context"] in allowed_contexts
            and row.get("parse_arguments")
            and row.get("working_directory")
            and Path(row["working_directory"]).is_absolute()
            for row in scope
        )
        and any(entry["path"] == report_name for entry in manifest["artifacts"])
    )


def analyze(
    config: EffectiveConfig, *, report_format: str = "html", timeout: float = 300
) -> dict[str, Any]:
    """Run analysis tools only, then retain an explicitly unverified-source archive.

    Target build scripts are never invoked. Artifact completeness and experimental
    analysis scores do not constitute verification evidence or a policy result.
    """
    if (
        report_format not in {"json", "html", "pdf"}
        or isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ContractError("Unsupported report format or nonpositive timeout")
    if config.execution["mode"] == "bounded":
        return _analyze_bounded(config, report_format=report_format, timeout=timeout)
    config.output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(
        prefix=".analysis-", dir=config.output, ignore_cleanup_errors=True
    ) as directory:
        work = Path(directory)
        try:
            from cppulse.history_boundary import mine_optional_history as mine
            from cppulse.predictor.main import run as predict

            settings = work / "settings.json"
            settings.write_text(json.dumps(config.settings, indent=2), encoding="utf-8")
            (work / "effective_config.json").write_text(
                json.dumps(config.as_dict(), indent=2), encoding="utf-8"
            )
            native = discover_native()
            argv = [
                str(native.analyzer),
                "--repo",
                str(config.repo),
                "--output",
                str(work),
                "--config",
                str(settings),
            ]
            if config.compilation_database:
                argv.extend(
                    ["--compilation-database", str(config.compilation_database)]
                )
            if native.resource_dir:
                argv.extend(["--resource-dir", str(native.resource_dir)])
            with (work / "analyzer.log").open("wb") as log:
                result = subprocess.run(
                    argv,
                    env=native.environment(),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                    shell=False,
                )
            if result.returncode:
                raise RuntimeError(
                    f"Native analyzer exited {result.returncode}: {(work / 'analyzer.log').read_text(errors='replace')[-2000:]}"
                )
            try:
                from cppulse.config import default_history

                history_status = (
                    mine(config.repo, work)
                    if config.history == default_history()
                    else mine(config.repo, work, options=config.history)
                )
                if history_status != 0:
                    raise RuntimeError("Git miner failed")
            except SystemExit as error:
                raise RuntimeError(f"Git miner exited {error.code}") from error
            try:
                predict(work, work, profile=config.settings["profile"])
            except SystemExit as error:
                raise RuntimeError(f"Predictor exited {error.code}") from error
            report_name = f"report.{report_format}"
            generate_report(work, report_format, work / report_name)
            summary = import_pipeline(work, config.repo, config.output)
            snapshot = RunStore(config.output).open_run(
                summary["run_id"], manifest_sha256=summary["manifest_sha256"]
            )
            summary["analysis_status"] = (
                "completed"
                if _legacy_analysis_completed(config, snapshot, report_name)
                else "partial"
            )
            # Flat files preserve original scripts. Snapshot readers, not these
            # separately replaced compatibility exports, provide coherent reads.
            for name in (
                *[f"{name}.json" for name in DOCUMENTS],
                report_name,
                "git_behavior.json",
                "git_history.json",
            ):
                source = work / name
                if not source.is_file():
                    continue
                target = config.output / name
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{name}.", suffix=".new", dir=config.output
                )
                os.close(descriptor)
                temporary = Path(temporary_name)
                try:
                    shutil.copyfile(source, temporary)
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
            summary.update(
                {
                    "execution_mode": "legacy",
                    "worker_limits_applied": False,
                    "run_path": str(snapshot.path),
                    "legacy_data": str(snapshot.path / "legacy"),
                    "report": (
                        str(snapshot.path / report_name)
                        if (snapshot.path / report_name).is_file()
                        else None
                    ),
                    "limitations": snapshot.manifest["limitations"],
                }
            )
            return summary
        except (Exception, KeyboardInterrupt) as error:
            # Retain diagnostics before TemporaryDirectory cleanup. A concurrent
            # publisher or storage failure must not replace the original error.
            try:
                _failed_attempt(config, error, started, work)
            except Exception as publication_error:
                logger.error("Could not retain failed attempt: %s", publication_error)
            raise


def generate_report(
    input_dir: Path,
    format: str,
    output: Path | None = None,
    *,
    evidence: bool = False,
    run_id: str | None = None,
    manifest_sha256: str | None = None,
    assessment_artifact_id: str | None = None,
) -> dict[str, Any]:
    """Render a legacy report or an explicitly selected checked evidence view."""
    if format not in {"json", "html", "pdf"}:
        raise ContractError(f"Unsupported report format: {format}")
    if (run_id is None) != (manifest_sha256 is None):
        raise ContractError("Report selection needs both run_id and manifest_sha256")
    if assessment_artifact_id is not None and not evidence:
        raise ContractError("Assessment selection requires evidence report mode")
    input_dir = input_dir.resolve(strict=True)
    snapshot = None
    store = None
    filename = ("evidence-report." if evidence else "report.") + format
    if (input_dir / "run_manifest.json").exists() or (
        input_dir / "run_manifest.json"
    ).is_symlink():
        if input_dir.parent.name != "runs":
            raise ContractError(
                "A concrete snapshot must be selected from its run store's runs directory"
            )
        store = RunStore.open_existing(input_dir.parent.parent)
        if run_id is not None and run_id != input_dir.name:
            raise ContractError("Report pin differs from the selected concrete run")
        snapshot = store.open_run(input_dir.name, manifest_sha256=manifest_sha256)
        default_output = store.root / "derived" / snapshot.run_id / filename
    elif any(
        (input_dir / name).exists() or (input_dir / name).is_symlink()
        for name in ("latest_attempt.json", "latest.json", "runs")
    ):
        store = RunStore.open_existing(input_dir)
        snapshot = (
            store.open_run(run_id, manifest_sha256=manifest_sha256)
            if run_id is not None
            else store.resolve_latest_attempt()
        )
        default_output = (
            store.root / "derived" / snapshot.run_id / filename
            if run_id is not None
            else input_dir / filename
        )
    else:
        if run_id is not None or evidence:
            raise ContractError(
                "Evidence or pinned reports require a checked run store"
            )
        default_output = input_dir / filename
    output = (output or default_output).resolve()
    if store is not None and (
        output.is_relative_to(store.root / "runs")
        or output.is_relative_to(store.root / ".staging")
        or output.is_relative_to(store.root / ".migration-v3")
        or (
            output.parent == store.root
            and output.name
            in {
                "latest.json",
                "latest_attempt.json",
                "heads.json",
                "store-format.json",
                ".coordination.lock",
                ".publication.lock",
                "run_manifest.json",
            }
        )
    ):
        raise ContractError(
            "Report output cannot modify immutable snapshots or run-store metadata"
        )
    if evidence:
        from cppulse.presentation import (
            build_snapshot_view,
            render_snapshot_html,
            render_snapshot_json,
            render_snapshot_pdf,
        )

        view = build_snapshot_view(
            snapshot, assessment_artifact_id=assessment_artifact_id
        )
        if format == "pdf":
            content = render_snapshot_pdf(view)
        elif format == "html":
            content = render_snapshot_html(view).encode("utf-8")
        else:
            content = render_snapshot_json(view).encode("utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        return {
            "report": str(output),
            "format": format,
            "run_id": snapshot.run_id,
            "manifest_sha256": snapshot.manifest_sha256,
            "mode": "snapshot_view",
            "bytes": len(content),
        }

    from cppulse.report_engine.pdf_generator import PDFGenerator

    with tempfile.TemporaryDirectory(prefix="cppulse-report-") as directory:
        data = Path(directory)
        run_id = None
        if snapshot is not None:
            run_id = snapshot.run_id
            if snapshot.manifest["status"] != "completed":
                raise RuntimeError(
                    f"Latest attempt {run_id} is {snapshot.manifest['status']}; select a concrete completed run for historical results"
                )
            for name in DOCUMENTS:
                (data / f"{name}.json").write_bytes(snapshot.read_bytes(name))
        else:
            for name in DOCUMENTS:
                (data / f"{name}.json").write_bytes(
                    (input_dir / f"{name}.json").read_bytes()
                )
        for name in DOCUMENTS:
            read_prototype_document(
                name, json.loads((data / f"{name}.json").read_bytes())
            )
        generator = PDFGenerator(data)
        if format == "pdf":
            content = generator.generate_pdf()
        elif format == "html":
            content = generator.render_html().encode("utf-8")
        else:
            content = json.dumps(generator._collect_data(), indent=2).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    return {
        "report": str(output),
        "format": format,
        "run_id": run_id,
        "bytes": len(content),
    }


def _publish_bounded(
    config: EffectiveConfig,
    execution: "AnalysisExecution",
    generated: Path,
    *,
    complete: bool,
    failure: BaseException | None = None,
    report_format: str = "html",
) -> "RunSnapshot":
    """Retain original native receipts and explicit input/output bindings once."""
    from cppulse.compatibility import read_risk_scores
    from cppulse.analysis_execution import (
        discover_sources,
        observe_source_inputs,
        verify_include_bindings,
        _database,
    )
    from cppulse.identities import hash_artifact, snapshot_inputs, verify_inputs
    from cppulse.errors import IntegrityError, InputChanged
    from cppulse.work_units import (
        _check,
        _resource_files,
        _resource_manifest,
        _write,
    )

    store = RunStore(config.output)
    with store.begin() as stage:
        inputs_by_content: dict[tuple[str, str], str] = {}
        bindings: list[dict[str, Any]] = []
        integrity_events: list[str] = []
        frozen_metadata: dict[Path, str] = {}
        result_pins = {row["unit_id"]: row for row in execution.summary["results"]}
        frozen_directory = generated / "frozen-execution"
        frozen_directory.mkdir(exist_ok=True)

        def metadata_digest(path: Path) -> str | None:
            try:
                return hash_artifact(
                    path, "observed", "observed.bin", "application/octet-stream"
                )["sha256"]
            except (ContractError, IntegrityError, InputChanged, OSError):
                return None

        def retain_frozen(
            identifier: str,
            original_path: Path,
            destination: str,
            document: Any,
            expected_sha256: str,
        ) -> None:
            if digest_json(document) != expected_sha256:
                raise IntegrityError(
                    "In-memory execution material differs from its frozen digest"
                )
            observed = metadata_digest(original_path)
            frozen_metadata[original_path] = expected_sha256
            if observed != expected_sha256:
                integrity_events.append(
                    "Post-execution material changed: "
                    + identifier
                    + "; exact digest-pinned original retained from frozen canonical bytes."
                )
                if original_path.is_file() and not original_path.is_symlink():
                    stage.copy_artifact(
                        identifier + ".changed",
                        original_path,
                        destination + ".changed",
                        "application/octet-stream",
                    )
            frozen = frozen_directory / (identifier + ".json")
            _write(frozen, document)
            copied = stage.copy_artifact(
                identifier, frozen, destination, "application/json"
            )
            if copied["sha256"] != expected_sha256:
                raise IntegrityError(
                    "Frozen execution material changed during publication"
                )

        for unit, result in execution.results:
            prefix = unit["artifact_prefix"]
            unit_root = Path(unit["work_root"])
            destination = f"execution/units/{unit['unit_id']}/{unit_root.name}"
            input_ids = {}
            for role, record in unit["inputs"].items():
                if record is None:
                    continue
                key = (record["sha256"], record["media_type"])
                identifier = inputs_by_content.get(key)
                if identifier is None:
                    identifier = "input-" + digest_json(
                        {"sha256": record["sha256"], "media_type": record["media_type"]}
                    )
                    extension = (
                        ".json"
                        if record["media_type"] == "application/json"
                        else ".bin"
                    )
                    retained = stage.copy_artifact(
                        identifier,
                        unit_root / record["path"],
                        f"execution/inputs/{record['sha256']}{extension}",
                        record["media_type"],
                    )
                    if any(
                        retained[field] != record[field]
                        for field in ("sha256", "size_bytes")
                    ):
                        raise IntegrityError("Bounded input changed while publishing")
                    inputs_by_content[key] = identifier
                input_ids[role] = identifier
            for record in result["artifacts"]:
                retained = stage.copy_artifact(
                    record["id"],
                    unit_root / record["path"],
                    destination + "/" + record["path"],
                    record["media_type"],
                )
                if any(
                    retained[field] != record[field]
                    for field in ("sha256", "size_bytes")
                ):
                    raise IntegrityError("Bounded output changed while publishing")
            request_id, result_id, receipt_id = (
                prefix + suffix for suffix in (".request", ".result", ".receipt")
            )
            pin = result_pins.get(unit["unit_id"])
            if pin is None or digest_json(unit) != result["request_sha256"]:
                raise IntegrityError(
                    "Unit request/result no longer matches frozen execution links"
                )
            retain_frozen(
                request_id,
                unit_root / "request.json",
                destination + "/request.json",
                unit,
                result["request_sha256"],
            )
            retain_frozen(
                result_id,
                unit_root / "result.json",
                destination + "/result.json",
                result,
                pin["sha256"],
            )
            checkpoint = {
                "version": "1.0.0",
                "request_sha256": result["request_sha256"],
                "result_sha256": pin["sha256"],
            }
            _check("work_checkpoint", checkpoint)
            retain_frozen(
                prefix + ".checkpoint",
                unit_root / "checkpoint.json",
                destination + "/checkpoint.json",
                checkpoint,
                digest_json(checkpoint),
            )
            # The receipt object is retained exactly: no new execution ID, argv,
            # timestamps, artifact IDs or successful execution is synthesized.
            stage.write_json(
                destination + "/receipt.json",
                result["execution_receipt"],
                contract="execution_receipt",
                artifact_id=receipt_id,
            )
            bindings.append(
                {
                    "unit_id": unit["unit_id"],
                    "request_artifact_id": request_id,
                    "result_artifact_id": result_id,
                    "receipt_artifact_id": receipt_id,
                    "inputs": input_ids,
                    "outputs": [row["id"] for row in result["artifacts"]],
                }
            )
        for rejected_unit, reason in execution.rejected:
            unit_root = Path(rejected_unit["work_root"])
            for name in (
                "request.json",
                "result.json",
                "checkpoint.json",
                "stdout.log",
                "stderr.log",
                "limits.json",
                "output/findings.json",
            ):
                selected = unit_root / name
                if selected.is_file() and not selected.is_symlink():
                    identifier = (
                        "rejected-"
                        + rejected_unit["unit_id"]
                        + "."
                        + name.replace("/", "-").replace(".", "-")
                    )
                    stage.copy_artifact(
                        identifier,
                        selected,
                        "diagnostics/rejected/" + rejected_unit["unit_id"] + "/" + name,
                        "application/octet-stream",
                    )
            integrity_events.append(
                "Rejected checkpoint was retained as diagnostic bytes, not an actual receipt: "
                + rejected_unit["unit_id"]
                + "; "
                + reason
            )
        _check("analysis_execution_plan", execution.plan)
        _check("analysis_execution_summary", execution.summary)
        _check("analysis_source_observations", execution.source_observations)
        retain_frozen(
            "analysis-plan",
            execution.work_root / "analysis-plan.json",
            "execution/analysis-plan.json",
            execution.plan,
            execution.summary["plan_sha256"],
        )
        if execution.compilation_database is not None:
            # Retain declarations even when every entry is unassessed and no
            # worker exists to carry a per-unit database input artifact.
            retain_frozen(
                "analysis-compilation-database",
                execution.work_root / "compile_commands.json",
                "execution/compile_commands.json",
                execution.compilation_database,
                execution.plan["compilation_database_sha256"],
            )
        retain_frozen(
            "source-observations",
            execution.work_root / "source-observations.json",
            "execution/source-observations.json",
            execution.source_observations,
            execution.summary["source_observations_sha256"],
        )
        retain_frozen(
            "analysis-summary",
            execution.summary_path,
            "execution/analysis-summary.json",
            execution.summary,
            digest_json(execution.summary),
        )
        binding_document = {
            "version": "1.0.0",
            "source_digest": execution.source["digest"],
            "units": bindings,
            "limitations": [
                "Input artifact mapping preserves local request identities without pretending aggregate JSON is one native invocation."
            ],
        }
        _check("analysis_execution_bindings", binding_document)
        _write(generated / "analysis-bindings.json", binding_document)
        stage.copy_artifact(
            "analysis-bindings",
            generated / "analysis-bindings.json",
            "execution/analysis-bindings.json",
            "application/json",
        )
        plan = execution.plan

        def source_check() -> None:
            errors = verify_inputs(config.repo, execution.source)
            database, database_digest = _database(
                config, config.execution["output_bytes"]
            )
            paths, gaps = discover_sources(config.repo, database)
            observations = execution.source_observations
            _check("analysis_source_observations", observations)
            if (
                observe_source_inputs(
                    config.repo, [row["path"] for row in execution.source["files"]]
                )
                != observations["after"]
            ):
                raise InputChanged(
                    "Source filesystem observations changed before bounded publication"
                )
            if (
                errors
                or paths != [row["path"] for row in execution.source["files"]]
                or gaps != plan["discovery_gaps"]
            ):
                raise InputChanged(
                    "Source inventory changed before bounded publication"
                )
            if database_digest != plan["compilation_database_sha256"]:
                raise InputChanged(
                    "Compilation database changed before bounded publication"
                )
            include_changes, include_unknown = verify_include_bindings(
                execution.results, execution.source
            )
            if include_changes or include_unknown:
                raise InputChanged(
                    "Native include buffer binding changed or is unavailable before publication"
                )
            checked_resources = set()
            checked_native = set()
            for unit, result in execution.results:
                native_path = result["execution_receipt"]["argv"][0]
                if native_path not in checked_native:
                    from cppulse.identities import hash_artifact

                    if (
                        hash_artifact(
                            native_path, "native", "native", "application/octet-stream"
                        )["sha256"]
                        != unit["native"]["sha256"]
                    ):
                        raise InputChanged(
                            "Native executable changed before bounded publication"
                        )
                    checked_native.add(native_path)
                resources = _resource_manifest(unit, Path(unit["work_root"]))
                if resources is not None and resources["root"] not in checked_resources:
                    actual = snapshot_inputs(
                        resources["root"], _resource_files(Path(resources["root"]))
                    )
                    if actual["files"] != resources["source"]["files"]:
                        raise InputChanged(
                            "Builtin resources changed before bounded publication"
                        )
                    checked_resources.add(resources["root"])

        # Retain only SDK buffers actually observed by a TU. These are separate
        # from selected project source, and remain unqualified until a consumer
        # checks their original request/report/inventory linkage.
        from cppulse.sdk_inputs import retain_used_sdk_inputs

        retain_used_sdk_inputs(stage, execution)
        verified = (
            execution.summary["input_verification"] == "verified"
            and not integrity_events
        )
        if verified:
            try:
                source_check()
            except (ContractError, IntegrityError, InputChanged, OSError):
                verified = False
        interrupted = isinstance(failure, KeyboardInterrupt)
        status = (
            "completed"
            if complete
            and verified
            and execution.summary["status"] == "completed"
            and not integrity_events
            else (
                "cancelled"
                if interrupted or execution.summary["status"] == "cancelled"
                else "partial"
            )
        )
        manifest = {
            "version": "2.0.0",
            "run_id": stage.run_id,
            "status": status,
            "source": execution.source,
            "contexts": execution.contexts,
            "stages": [
                {
                    "id": "bounded-native-analysis",
                    "status": (
                        "passed"
                        if execution.summary["status"] == "completed" and verified
                        else "cancelled" if status == "cancelled" else "error"
                    ),
                    "depends_on": [],
                    "reason": "Original independent native execution receipts retained; compatibility aggregation is not a native invocation.",
                },
                {
                    "id": "pipeline-consumers",
                    "status": (
                        "passed"
                        if complete
                        else "cancelled" if interrupted else "error"
                    ),
                    "depends_on": ["bounded-native-analysis"],
                    "reason": (
                        "Git, prediction and presentation functions completed."
                        if complete
                        else str(failure) or "Consumers did not complete."
                    ),
                },
            ],
            "artifacts": stage.artifacts,
            "started_at": execution.summary["started_at"],
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "config_digest": digest_json(config.as_dict()),
            "versions": {"cppulse": __version__},
            "limitations": [
                *execution.summary["limitations"],
                *integrity_events,
                *(
                    [
                        "Source or context inputs changed; current verified input binding is unavailable."
                    ]
                    if not verified
                    else []
                ),
                "No target build/test/sanitizer recipe was executed. Source binding and native analysis are not verification or policy approval.",
                "Experimental compatibility risk data is retained separately; raw per-unit facts and receipts remain primary.",
            ],
        }
        manifest["stages"].append(
            {
                "id": "publication-integrity",
                "status": "failed" if integrity_events else "passed",
                "depends_on": ["bounded-native-analysis"],
                "reason": (
                    "Changed workspace metadata was quarantined; original digests verified."
                    if integrity_events
                    else "Original execution metadata and artifact digests match."
                ),
            }
        )
        from cppulse.work_unit_analysis import append_work_unit_analysis

        # A projection is checked owned staged material, not a published run or
        # a synthetic snapshot. No reader pointer changes until all final facts
        # and health exist and the strong current-input check succeeds again.
        try:
            material = stage.project(
                manifest, source_check=source_check if verified else None
            )
        except InputChanged:
            # No typed facts have been written yet, so the raw frozen material
            # can still be interpreted honestly as an unverified partial run.
            verified = False
            manifest["status"] = "partial"
            manifest["stages"][0]["status"] = "error"
            manifest["limitations"].append(
                "Inputs changed before staged normalization; no current verified source claim is made."
            )
            material = stage.project(manifest)
        final_manifest = append_work_unit_analysis(
            stage, material, profile=config.settings["profile"]
        )
        # Existing retained-unit normalization decides prerequisite availability
        # before compatibility consumers run. Prediction still executes once;
        # no finding count or projection can stand in for missing typed evidence.
        if complete:
            from cppulse.predictor.main import run as predict

            qualified = stage.project(
                final_manifest, source_check=source_check if verified else None
            )
            health_entries = [
                entry
                for entry in final_manifest["artifacts"]
                if entry.get("contract", {}).get("kind") == "maintenance_health"
            ]
            health = (
                qualified.read_json(health_entries[0]["id"])
                if len(health_entries) == 1
                else None
            )
            try:
                predict(
                    generated,
                    generated,
                    profile=config.settings["profile"],
                    maintenance_health=health,
                    source_digest=execution.source["digest"],
                )
            except SystemExit as error:
                raise RuntimeError(f"Pipeline consumer exited {error.code}") from error
            generate_report(
                generated, report_format, generated / f"report.{report_format}"
            )
        for name in DOCUMENTS:
            path = generated / f"{name}.json"
            if path.is_file():
                if not complete and name in {"risk_scores", "roadmap"}:
                    stage.copy_artifact(
                        "failed-" + name,
                        path,
                        f"diagnostics/failed-consumers/{name}.json",
                        "application/json",
                    )
                    continue
                stage.copy_artifact(
                    name,
                    path,
                    f"legacy/{name}.json",
                    "application/json",
                    contract=(name, "prototype_v1") if complete else None,
                )
        risk_path = generated / "risk_scores.json"
        if complete and risk_path.is_file():
            normalized = read_risk_scores(
                json.loads(risk_path.read_bytes()), allow_prototype_v1=True
            )
            stage.write_json(
                "normalized/risk_scores.json",
                normalized,
                contract="risk_scores",
                artifact_id="normalized-risk",
            )
        for name, media in (
            ("report.pdf", "application/pdf"),
            ("report.html", "text/html"),
            ("report.json", "application/json"),
            ("analyzer.log", "text/plain"),
            ("effective_config.json", "application/json"),
            ("git_behavior.json", "application/json"),
            ("git_history.json", "application/json"),
        ):
            path = generated / name
            if path.is_file():
                if not complete and name.startswith("report."):
                    stage.copy_artifact(
                        "failed-" + name.replace(".", "-"),
                        path,
                        "diagnostics/failed-consumers/" + name,
                        media,
                    )
                    continue
                stage.copy_artifact(name.replace(".", "-"), path, name, media)
        if not complete and any(
            entry["id"].startswith("failed-") for entry in stage.artifacts
        ):
            final_manifest["limitations"].append(
                "Failed consumer outputs are retained as diagnostic bytes; they do not supply current qualified health or recommendations."
            )
        final_manifest["artifacts"] = stage.artifacts

        def metadata_check() -> None:
            if not complete or integrity_events:
                return
            for path, expected in frozen_metadata.items():
                if metadata_digest(path) != expected:
                    raise InputChanged(
                        "Frozen work-unit metadata changed before bounded publication"
                    )

        # Never demote already-written qualified facts after a final race.
        # A failure retains the owned stage and leaves every reader pointer
        # untouched; outer failure handling can construct a fresh partial run.
        snapshot = stage.publish(
            final_manifest,
            source_check=source_check if verified else None,
            material_check=metadata_check,
        )
    try:
        from cppulse.analysis_execution import index_published_execution

        index_published_execution(snapshot, config.output / "work-units.sqlite")
    except Exception as error:
        logger.warning(
            "Immutable facts are retained; derived work-unit index can be rebuilt: %s",
            error,
        )
    return snapshot


def _analyze_bounded(
    config: EffectiveConfig, *, report_format: str, timeout: float
) -> dict[str, Any]:
    """Public bounded native journey with coherent current/failure snapshots."""
    from cppulse.analysis_execution import run_analysis
    from cppulse.config import default_history

    config.output.mkdir(parents=True, exist_ok=True)
    # Native input/output roots remain outside source, including when the store
    # is requested beneath the repository itself.
    persistent = config.execution["work_directory"] is not None
    directory = (
        tempfile.mkdtemp(prefix="cppulse-bounded-")
        if not persistent
        else config.execution["work_directory"]
    )
    generated = Path(tempfile.mkdtemp(prefix=".analysis-", dir=config.output))
    execution = None
    published = False
    try:
        native = discover_native()
        execution = run_analysis(config, native, Path(directory), timeout=timeout)
        if execution.summary.get("interruption") == "keyboard_interrupt":
            _publish_bounded(
                config,
                execution,
                generated,
                complete=False,
                failure=KeyboardInterrupt(
                    "Native analysis interrupted before consumers"
                ),
            )
            published = True
            raise KeyboardInterrupt
        shutil.copyfile(execution.report_path, generated / "findings.json")
        (generated / "effective_config.json").write_text(
            json.dumps(config.as_dict(), indent=2)
        )
        (generated / "analyzer.log").write_text(
            f"Bounded native units: {execution.summary['unit_count']}; status: {execution.summary['status']}. Original per-unit stdout/stderr and receipts are retained in execution artifacts.\n"
        )
        from cppulse.history_boundary import mine_optional_history as mine

        try:
            status = (
                mine(config.repo, generated)
                if config.history == default_history()
                else mine(config.repo, generated, options=config.history)
            )
            if status != 0:
                raise RuntimeError("Git miner failed")
        except SystemExit as error:
            raise RuntimeError(f"Pipeline consumer exited {error.code}") from error
        snapshot = _publish_bounded(
            config, execution, generated, complete=True, report_format=report_format
        )
        published = True
        catalog_path = config.output / "work-units.sqlite"
        catalog_status = "ready"
        try:
            from cppulse.work_unit_store import WorkUnitIndex

            WorkUnitIndex(catalog_path, read_only=True).page(
                snapshot.run_id, snapshot.manifest_sha256, page_size=1
            )
        except Exception:
            catalog_status = "unavailable"
        risk = json.loads((generated / "risk_scores.json").read_bytes())
        analysis_status = (
            "completed"
            if execution.summary["status"] == "completed"
            and snapshot.manifest["status"] == "completed"
            and snapshot.manifest["input_verification"] == "verified"
            else "partial"
        )
        for name in (
            *[f"{name}.json" for name in DOCUMENTS],
            f"report.{report_format}",
            "git_behavior.json",
            "git_history.json",
        ):
            source = generated / name
            if source.is_file():
                descriptor, temporary = tempfile.mkstemp(
                    prefix=f".{name}.", suffix=".new", dir=config.output
                )
                os.close(descriptor)
                target = Path(temporary)
                try:
                    shutil.copyfile(source, target)
                    target.replace(config.output / name)
                finally:
                    target.unlink(missing_ok=True)
        return {
            "operation": "bounded-analysis",
            "execution_mode": "bounded",
            "run_id": snapshot.run_id,
            "manifest_sha256": snapshot.manifest_sha256,
            "store": str(config.output),
            "run_path": str(snapshot.path),
            "legacy_data": str(snapshot.path / "legacy"),
            "report": str(snapshot.path / f"report.{report_format}"),
            "input_verification": snapshot.manifest["input_verification"],
            "analysis_status": analysis_status,
            "health_availability": risk["health_score"].get("status", "no_data"),
            "execution_status": execution.summary["status"],
            "work_unit_catalog": str(catalog_path),
            "catalog_status": catalog_status,
            "unit_count": execution.summary["unit_count"],
            "resumed_units": execution.summary["resumed_units"],
            "outcomes": execution.summary["outcomes"],
            "requested_execution": config.execution,
            "worker_limits_applied": "See each retained native capability report; no aggregate enforcement claim.",
            "limitations": snapshot.manifest["limitations"],
        }
    except (Exception, KeyboardInterrupt) as error:
        if execution is None:
            try:
                _failed_attempt(
                    config, error, datetime.now(timezone.utc).isoformat(), generated
                )
            except Exception:
                logger.exception("Could not publish bounded preparation failure")
        if execution is not None and not published:
            try:
                _publish_bounded(
                    config, execution, generated, complete=False, failure=error
                )
                published = True
            except Exception:
                logger.exception(
                    "Could not publish bounded failure facts; execution retained at %s",
                    directory,
                )
        raise
    finally:
        if published:
            shutil.rmtree(generated, ignore_errors=True)
        else:
            logger.warning("Unpublished pipeline diagnostics retained at %s", generated)
        if not persistent and published:
            shutil.rmtree(directory, ignore_errors=True)
        elif not persistent:
            logger.warning("Unpublished bounded execution retained at %s", directory)
