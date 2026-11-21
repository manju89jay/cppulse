"""Operational failures remain visible without losing their generated diagnostics."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cppulse.config import effective_config
from cppulse.errors import ContractError, IntegrityError, PublicationConflict
from cppulse.importer import import_pipeline
from cppulse.pipeline import analyze, generate_report
from cppulse.run_store import RunStore
import test_pipeline_snapshot_import as import_fixtures

bundle = import_fixtures.bundle


def stub_native(
    monkeypatch: pytest.MonkeyPatch,
    *,
    exit_code: int = 0,
    findings: Path | None = None,
) -> None:
    """A transparent process stub exercises orchestration without any build."""
    import cppulse.pipeline as pipeline

    native = SimpleNamespace(
        analyzer=Path("/synthetic/cppulse-analyzer"),
        resource_dir=None,
        environment=lambda: {},
    )
    monkeypatch.setattr(pipeline, "discover_native", lambda: native)

    def run(*args: Any, **kwargs: Any) -> SimpleNamespace:
        kwargs["stdout"].write(b"synthetic analyzer diagnostic\n")
        if findings is not None:
            argv = args[0]
            destination = Path(argv[argv.index("--output") + 1])
            (destination / "findings.json").write_bytes(findings.read_bytes())
        return SimpleNamespace(returncode=exit_code)

    # Replace only pipeline's process adapter. Patching subprocess.run globally
    # also intercepts dependency import probes (for example NumPy's lscpu).
    monkeypatch.setattr(
        pipeline,
        "subprocess",
        SimpleNamespace(run=run, STDOUT=pipeline.subprocess.STDOUT),
    )


@pytest.mark.parametrize("missing_findings", [False, True])
def test_component_system_exit_records_partial_attempt(
    bundle: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    missing_findings: bool,
) -> None:
    import cppulse.git_miner.main as miner

    flat, source, store_root = bundle
    import_pipeline(flat, source, store_root, run_id="prior")
    stub_native(
        monkeypatch, findings=None if missing_findings else flat / "findings.json"
    )
    # The predictor checks native bytes before opening the missing Git input.
    monkeypatch.setattr(miner, "run", lambda *args: 0)
    error, message = (
        (IntegrityError, "Native predictor input is missing or unsafe")
        if missing_findings
        else (RuntimeError, "[Pp]redictor.*1")
    )
    with pytest.raises(error, match=message):
        analyze(effective_config(source, store_root), report_format="json")
    store = RunStore(store_root)
    assert store.resolve_latest().run_id == "prior"
    attempted = store.resolve_latest_attempt()
    assert attempted.run_id != "prior"
    assert attempted.manifest["status"] == "partial"


def test_failed_analyzer_retains_log_and_configuration(
    bundle: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    flat, source, store_root = bundle
    import_pipeline(flat, source, store_root, run_id="prior")
    stub_native(monkeypatch, exit_code=7)
    with pytest.raises(RuntimeError, match="exited 7"):
        analyze(effective_config(source, store_root), report_format="json")
    store = RunStore(store_root)
    failed = store.resolve_latest_attempt()
    assert failed.manifest["status"] == "partial"
    assert failed.read_bytes("analyzer-log") == b"synthetic analyzer diagnostic\n"
    assert b'"profile": "default"' in failed.read_bytes("effective_config-json")
    assert b"exited 7" in failed.read_bytes("failure")
    assert store.resolve_latest().run_id == "prior"
    assert not list(store_root.glob(".analysis-*"))


def test_failure_publication_does_not_mask_original_error(
    bundle: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import cppulse.pipeline as pipeline

    _, source, store_root = bundle
    stub_native(monkeypatch, exit_code=7)

    def unavailable_store(*args: Any, **kwargs: Any) -> None:
        raise PublicationConflict("synthetic concurrent publisher")

    monkeypatch.setattr(pipeline, "_failed_attempt", unavailable_store)
    with pytest.raises(RuntimeError, match="exited 7"):
        analyze(effective_config(source, store_root), report_format="json")
    assert "synthetic concurrent publisher" in caplog.text
    assert "failed attempt" in caplog.text.lower()


def test_historical_snapshot_report_reads_checked_bytes_and_writes_derived_output(
    bundle: tuple[Path, Path, Path],
) -> None:
    flat, source, store_root = bundle
    import_pipeline(flat, source, store_root, run_id="historical")
    snapshot = RunStore(store_root).open_run("historical")
    original = snapshot.read_bytes("findings")
    result = generate_report(snapshot.path, "html")
    output = Path(result["report"])
    assert result["run_id"] == "historical"
    assert not output.is_relative_to(snapshot.path)
    assert "cppulse" in output.read_text()
    assert snapshot.read_bytes("findings") == original
    snapshot.verify()


def test_report_cannot_overwrite_immutable_snapshot_artifacts(
    bundle: tuple[Path, Path, Path],
) -> None:
    flat, source, store_root = bundle
    import_pipeline(flat, source, store_root, run_id="historical")
    snapshot = RunStore(store_root).open_run("historical")
    target = snapshot.path / "legacy/findings.json"
    original = target.read_bytes()
    with pytest.raises(ContractError, match="[Ii]mmutable|snapshot"):
        generate_report(store_root, "json", target)
    assert target.read_bytes() == original
    snapshot.verify()


def test_compatibility_export_does_not_clobber_another_writers_temporary_file(
    bundle: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flat, source, store_root = bundle
    store_root.mkdir()
    another_export = store_root / ".findings.json.new"
    another_export.write_bytes(b"another writer's pending export")
    stub_native(monkeypatch, findings=flat / "findings.json")
    result = analyze(effective_config(source, store_root), report_format="json")
    assert another_export.read_bytes() == b"another writer's pending export"
    assert (store_root / "findings.json").read_bytes() == (
        flat / "findings.json"
    ).read_bytes()
    snapshot = RunStore(store_root).open_run(result["run_id"])
    snapshot.verify()
    assert snapshot.manifest["input_verification"] == "unverified"
    assert list(store_root.glob(".findings.json.*.new")) == []
