"""Public bounded analyze retains source-bound facts and independent receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cppulse.config import effective_config
from cppulse.errors import InputChanged, IntegrityError
from cppulse.pipeline import analyze
from cppulse.run_store import RunStore
from cppulse.work_units import _check
import test_analysis_execution as fixtures
from cppulse.native import NativeInstallation


@pytest.fixture
def native() -> NativeInstallation:
    return fixtures.native.__wrapped__()


def config(tmp_path: Path, *, output_inside: bool = False, **options: Any):
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    (source / "main.cpp").write_text("int value() { return 1; }\n")
    output = source / "output" if output_inside else tmp_path / "store"
    return effective_config(
        source,
        output,
        execution={
            "mode": "bounded",
            "jobs": 2,
            "work_directory": str(tmp_path / "work"),
            **options,
        },
        history={"enabled": False},
    )


def select_native(monkeypatch: pytest.MonkeyPatch, native: Any) -> None:
    import cppulse.pipeline as pipeline

    monkeypatch.setattr(pipeline, "discover_native", lambda: native)


def private_json(snapshot: Any, identifier: str, kind: str) -> dict[str, Any]:
    document = json.loads(snapshot.read_bytes(identifier))
    _check(kind, document)
    return document


def test_public_bounded_analyze_retains_original_receipts_and_current_source(
    tmp_path: Path, native: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    select_native(monkeypatch, native)
    cfg = config(tmp_path)
    (cfg.repo / "library.hpp").write_text("inline int twice(int x) { return x * 2; }\n")
    summary = analyze(cfg, report_format="json", timeout=60)
    assert summary["operation"] == "bounded-analysis"
    assert summary["analysis_status"] == "completed"
    assert summary["input_verification"] == "verified"
    snapshot = RunStore(cfg.output).open_run(summary["run_id"])
    snapshot.verify()
    bindings = private_json(
        snapshot, "analysis-bindings", "analysis_execution_bindings"
    )
    _check("analysis_execution_bindings", bindings)
    assert len(bindings["units"]) == 2
    assert len(snapshot.manifest["source"]["files"]) == 2
    for row in bindings["units"]:
        original = private_json(snapshot, row["result_artifact_id"], "work_result")
        receipt = snapshot.read_json(row["receipt_artifact_id"])
        assert receipt == original["execution_receipt"]
        assert receipt["source_digest"] == snapshot.manifest["source"]["digest"]
        assert set(receipt["artifact_ids"] + receipt["log_artifact_ids"]) <= {
            artifact["id"] for artifact in snapshot.manifest["artifacts"]
        }
    assert not any(
        stage["id"] == "archive-import" for stage in snapshot.manifest["stages"]
    )
    assert json.loads(Path(summary["report"]).read_bytes())


def test_public_resume_runs_fresh_and_store_inside_repo_scope_stays_finite(
    tmp_path: Path, native: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    select_native(monkeypatch, native)
    cfg = config(tmp_path, output_inside=True)
    first = analyze(cfg, report_format="json", timeout=60)
    cfg.execution["resume"] = True
    second = analyze(cfg, report_format="json", timeout=60)
    assert second["resumed_units"] == 0
    store = RunStore(cfg.output)
    first_snapshot, second_snapshot = store.open_run(first["run_id"]), store.open_run(
        second["run_id"]
    )
    assert len(second_snapshot.manifest["source"]["files"]) == 1
    old = private_json(
        first_snapshot, "analysis-bindings", "analysis_execution_bindings"
    )["units"][0]
    new = private_json(
        second_snapshot, "analysis-bindings", "analysis_execution_bindings"
    )["units"][0]
    assert first_snapshot.read_json(
        old["receipt_artifact_id"]
    ) != second_snapshot.read_json(new["receipt_artifact_id"])
    assert first_snapshot.read_json(old["receipt_artifact_id"])["status"] == "passed"
    assert second_snapshot.read_json(new["receipt_artifact_id"])["status"] == "passed"


def test_native_failure_remains_partial_with_real_failed_receipt(
    tmp_path: Path, native: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    select_native(monkeypatch, native)
    cfg = config(tmp_path, address_space_bytes=1)
    summary = analyze(cfg, report_format="json", timeout=60)
    assert summary["analysis_status"] == "partial"
    assert summary["outcomes"]["process_error"] == 1
    snapshot = RunStore(cfg.output).resolve_latest_attempt()
    assert snapshot.manifest["status"] == "partial"
    binding = private_json(
        snapshot, "analysis-bindings", "analysis_execution_bindings"
    )["units"][0]
    receipt = snapshot.read_json(binding["receipt_artifact_id"])
    assert receipt["exit_code"] == 2
    assert receipt["status"] == "failed"
    assert (
        snapshot.read_json("findings")["metadata"]["analysis"]["files"][0]["status"]
        == "failed"
    )


def test_consumer_failure_retains_raw_producer_facts_and_previous_completed_run(
    tmp_path: Path, native: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.predictor.main as predictor

    select_native(monkeypatch, native)
    cfg = config(tmp_path)
    prior = analyze(cfg, report_format="json", timeout=60)

    def failing_consumer(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("authored downstream failure")

    monkeypatch.setattr(predictor, "run", failing_consumer)
    with pytest.raises(RuntimeError, match="authored downstream failure"):
        analyze(cfg, report_format="json", timeout=60)
    store = RunStore(cfg.output)
    failed = store.resolve_latest_attempt()
    assert failed.run_id != prior["run_id"]
    assert store.resolve_latest().run_id == prior["run_id"]
    assert failed.manifest["status"] == "partial"
    assert private_json(failed, "analysis-bindings", "analysis_execution_bindings")[
        "units"
    ]
    assert any(
        entry.get("contract", {}).get("kind") == "execution_receipt"
        for entry in failed.manifest["artifacts"]
    )
    from cppulse.work_unit_store import WorkUnitIndex

    rows, _ = WorkUnitIndex(cfg.output / "work-units.sqlite", read_only=True).page(
        failed.run_id, failed.manifest_sha256
    )
    assert rows and rows[0]["outcome"] == "complete"


def test_source_change_before_publication_cannot_keep_current_verified_claim(
    tmp_path: Path, native: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.pipeline as pipeline

    select_native(monkeypatch, native)
    cfg = config(tmp_path)
    original = pipeline.generate_report

    def mutate_after_report(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        (cfg.repo / "main.cpp").write_text("int changed_after_analysis;\n")
        return result

    monkeypatch.setattr(pipeline, "generate_report", mutate_after_report)
    # Reports now follow prerequisite normalization. A subsequent source race
    # must preserve those unpublished facts and fail the final strong check.
    with pytest.raises(InputChanged):
        analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).resolve_latest_attempt()
    assert snapshot.manifest["status"] == "partial"
    assert snapshot.manifest["input_verification"] == "unverified"
    assert any("inputs changed" in line for line in snapshot.manifest["limitations"])
    assert not any(
        row["id"] in {"risk_scores", "normalized-risk", "report-json", "roadmap"}
        for row in snapshot.manifest["artifacts"]
    )
    assert any(
        row["path"].startswith("diagnostics/failed-consumers/")
        for row in snapshot.manifest["artifacts"]
    )


def test_work_root_overlap_is_rejected_and_records_failure_attempt(
    tmp_path: Path, native: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    select_native(monkeypatch, native)
    cfg = config(tmp_path)
    cfg.execution["work_directory"] = str(cfg.repo / "unsafe-work")
    with pytest.raises(IntegrityError):
        analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).resolve_latest_attempt()
    assert snapshot.manifest["status"] == "partial"
    assert snapshot.manifest["input_verification"] == "unverified"
    assert not (cfg.repo / "unsafe-work").exists()


@pytest.mark.parametrize("mode", ["legacy", "bounded"])
@pytest.mark.parametrize(
    "format_value,timeout",
    [
        ("unsupported", 20),
        ("json", float("nan")),
        ("json", float("inf")),
        ("json", True),
        ("json", 0),
    ],
)
def test_bad_public_arguments_fail_before_native_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    format_value: str,
    timeout: Any,
) -> None:
    import cppulse.pipeline as pipeline

    cfg = effective_config(tmp_path, tmp_path / "output", execution={"mode": mode})

    def unexpected() -> None:
        raise AssertionError("Invalid public inputs must not discover or launch native")

    monkeypatch.setattr(pipeline, "discover_native", unexpected)
    from cppulse.errors import ContractError

    with pytest.raises(ContractError):
        analyze(cfg, report_format=format_value, timeout=timeout)
    assert not cfg.output.exists()


def test_manual_interrupt_publishes_cancelled_facts_without_starting_consumers(
    tmp_path: Path, native: NativeInstallation, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.analysis_execution as engine
    import cppulse.history_boundary as history
    import cppulse.predictor.main as predictor
    import cppulse.pipeline as pipeline

    select_native(monkeypatch, native)
    cfg = config(tmp_path)
    original = engine.execute_work_units

    def interrupted_after_native(*args: Any, **kwargs: Any):
        for result in original(*args, **kwargs):
            yield result
        raise KeyboardInterrupt

    def no_consumer(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Manual cancellation must not start downstream consumers")

    monkeypatch.setattr(engine, "execute_work_units", interrupted_after_native)
    monkeypatch.setattr(history, "mine_optional_history", no_consumer)
    monkeypatch.setattr(predictor, "run", no_consumer)
    monkeypatch.setattr(pipeline, "generate_report", no_consumer)
    with pytest.raises(KeyboardInterrupt):
        analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).resolve_latest_attempt()
    assert snapshot.manifest["status"] == "cancelled"
    assert private_json(snapshot, "analysis-bindings", "analysis_execution_bindings")[
        "units"
    ]
    assert (
        json.loads(snapshot.read_bytes("analysis-summary"))["interruption"]
        == "keyboard_interrupt"
    )
    assert not any(
        row["id"] in ("risk_scores", "git_metrics", "report-json")
        for row in snapshot.manifest["artifacts"]
    )
    from cppulse.work_unit_store import WorkUnitIndex

    rows, _ = WorkUnitIndex(cfg.output / "work-units.sqlite", read_only=True).page(
        snapshot.run_id, snapshot.manifest_sha256
    )
    assert rows and rows[0]["unit_id"]


def test_actual_cli_sigint_drains_workers_and_returns_130(
    tmp_path: Path, native: NativeInstallation
) -> None:
    import os
    import signal
    import subprocess
    import sys
    import time

    source = tmp_path / "source"
    source.mkdir()
    (source / "a-good.cpp").write_text("int value() { return 1; }\n")
    (source / "b-wait.cpp").write_text("int waiting;\n")
    ready = tmp_path / "worker-ready.pid"
    proxy = tmp_path / "cppulse-analyzer-proxy"
    proxy.write_text(
        "#!" + sys.executable + "\n"
        "import json,os,sys,time\nfrom pathlib import Path\n"
        "selection = json.loads(Path(sys.argv[sys.argv.index('--file-list')+1]).read_text())\n"
        "if selection == ['b-wait.cpp']:\n"
        "    ready=Path(os.environ['CPPULSE_TEST_READY'])\n"
        "    ready.with_suffix('.tmp').write_text(str(os.getpid()))\n"
        "    ready.with_suffix('.tmp').replace(ready)\n"
        "    time.sleep(30)\n"
        "real=os.environ['CPPULSE_TEST_REAL_NATIVE']\n"
        "os.execv(real,[real,*sys.argv[1:]])\n"
    )
    proxy.chmod(0o755)
    environment = dict(os.environ)
    environment.update(
        CPPULSE_ANALYZER=str(proxy),
        CPPULSE_TEST_READY=str(ready),
        CPPULSE_TEST_REAL_NATIVE=str(native.analyzer),
    )
    output = tmp_path / "store"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "cppulse",
            "analyze",
            "--repo",
            str(source),
            "--output",
            str(output),
            "--execution",
            "bounded",
            "--jobs",
            "1",
            "--no-history",
            "--format",
            "json",
            "--work-directory",
            str(tmp_path / "work"),
            "--timeout",
            "60",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 40
        while not ready.exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.02)
        assert (
            ready.exists()
        ), "Real first native unit must finish and second worker reach ready boundary"
        os.kill(process.pid, signal.SIGINT)
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 130, (stdout.decode(), stderr.decode())
        snapshot = RunStore(output).resolve_latest_attempt()
        assert snapshot.manifest["status"] == "cancelled"
        summary = json.loads(snapshot.read_bytes("analysis-summary"))
        assert summary["interruption"] == "keyboard_interrupt"
        assert summary["outcomes"]["complete"] == 1
        assert summary["outcomes"]["cancelled"] == 1
        assert not any(
            row["id"] in ("git_metrics", "risk_scores", "report-json")
            for row in snapshot.manifest["artifacts"]
        )
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        if ready.exists():
            pid = int(ready.read_text())
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_published_bounded_run_is_queryable_through_pinned_catalog_api(
    tmp_path: Path, native: NativeInstallation, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient
    from cppulse.report_engine.api import app
    from cppulse.work_unit_store import WorkUnitIndex

    select_native(monkeypatch, native)
    cfg = config(tmp_path)
    (cfg.repo / "other.hpp").write_text("inline int other() { return 2; }\n")
    result = analyze(cfg, report_format="json", timeout=60)
    assert result["catalog_status"] == "ready"
    catalog = Path(result["work_unit_catalog"])
    reader = WorkUnitIndex(catalog, read_only=True)
    rows, cursor = reader.page(result["run_id"], result["manifest_sha256"], page_size=1)
    assert len(rows) == 1 and cursor is not None
    monkeypatch.setenv("CPPULSE_WORK_UNIT_CATALOG", str(catalog))
    monkeypatch.setenv("CPPULSE_API_KEY", "authored-test-key")
    monkeypatch.setenv("DATA_DIR", str(cfg.output))
    with TestClient(app) as client:
        parameters = {
            "run_id": result["run_id"],
            "manifest_sha256": result["manifest_sha256"],
            "page_size": 1,
        }
        assert client.get("/api/v1/work-units", params=parameters).status_code == 401
        response = client.get(
            "/api/v1/work-units",
            params=parameters,
            headers={"Authorization": "Bearer authored-test-key"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["items"][0]["primary_file"] in ("main.cpp", "other.hpp")
        assert body["next_cursor"]
        parameters["cursor"] = body["next_cursor"]
        next_page = client.get(
            "/api/v1/work-units",
            params=parameters,
            headers={"Authorization": "Bearer authored-test-key"},
        ).json()
        assert next_page["items"][0]["unit_id"] != body["items"][0]["unit_id"]


def test_catalog_rebuild_uses_immutable_run_after_source_and_work_are_removed(
    tmp_path: Path, native: NativeInstallation, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil
    from cppulse.analysis_execution import index_published_execution
    from cppulse.work_unit_store import WorkUnitIndex

    select_native(monkeypatch, native)
    cfg = config(tmp_path)
    result = analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).open_run(result["run_id"])
    shutil.rmtree(cfg.repo)
    shutil.rmtree(cfg.execution["work_directory"])
    rebuilt = tmp_path / "rebuilt.sqlite"
    index_published_execution(snapshot, rebuilt)
    rows, cursor = WorkUnitIndex(rebuilt, read_only=True).page(
        snapshot.run_id, snapshot.manifest_sha256
    )
    assert rows[0]["primary_file"] == "main.cpp"
    assert rows[0]["input_verification"] == "verified"
    assert rows[0]["execution_status"] == "completed"
    assert cursor is None
