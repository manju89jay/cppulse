"""Installed native/Python analysis, retaining compatibility output and snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

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


def analyze(
    config: EffectiveConfig, *, report_format: str = "html", timeout: float = 300
) -> dict[str, Any]:
    """Run analysis tools only, then retain an explicitly unverified-source archive.

    Target build scripts are never invoked. Artifact completeness and experimental
    analysis scores do not constitute verification evidence or a policy result.
    """
    if report_format not in {"json", "html", "pdf"} or timeout <= 0:
        raise ContractError("Unsupported report format or nonpositive timeout")
    config.output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(
        prefix=".analysis-", dir=config.output, ignore_cleanup_errors=True
    ) as directory:
        work = Path(directory)
        try:
            from cppulse.git_miner.main import run as mine
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
                if mine(config.repo, work) != 0:
                    raise RuntimeError("Git miner failed")
            except SystemExit as error:
                raise RuntimeError(f"Git miner exited {error.code}") from error
            try:
                predict(work, work, profile=config.settings["profile"])
            except SystemExit as error:
                raise RuntimeError(f"Predictor exited {error.code}") from error
            generate_report(work, report_format, work / f"report.{report_format}")
            summary = import_pipeline(work, config.repo, config.output)
            snapshot = RunStore(config.output).open_run(summary["run_id"])
            health = snapshot.read_json("risk_scores")["health_score"]
            # A completed archive import only means artifacts were retained.
            # Keep the producer's analysis availability separate so the public
            # CLI cannot report a partial or source-free run as success.
            summary["analysis_status"] = (
                "completed"
                if health.get("status") == "scored" and health["overall"] is not None
                else "partial"
            )
            # Flat files preserve original scripts. Snapshot readers, not these
            # separately replaced compatibility exports, provide coherent reads.
            for name in (
                *[f"{name}.json" for name in DOCUMENTS],
                f"report.{report_format}",
            ):
                source = work / name
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
                    "run_path": str(snapshot.path),
                    "legacy_data": str(snapshot.path / "legacy"),
                    "report": str(snapshot.path / f"report.{report_format}"),
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
        or (
            output.parent == store.root
            and output.name
            in {
                "latest.json",
                "latest_attempt.json",
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
