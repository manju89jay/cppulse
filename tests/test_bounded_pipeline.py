"""Public bounded analyze retains source-bound facts and independent receipts."""

from __future__ import annotations

from collections.abc import Callable
import errno
from html import escape
import json
import os
from pathlib import Path
import shutil
from typing import Any

import pytest

from cppulse.config import effective_config
from cppulse.errors import InputChanged, IntegrityError
from cppulse.native import NativeInstallation
from cppulse.pipeline import analyze
from cppulse.presentation import (
    build_snapshot_view,
    render_snapshot_html,
    render_snapshot_json,
)
from cppulse.run_store import RunSnapshot, RunStore
from cppulse.work_units import _check
import test_analysis_execution as fixtures


INPUT_CHANGED = "Source or context inputs changed during bounded analysis."
INPUT_UNAVAILABLE = (
    "Source or context inputs could not be verified for bounded analysis."
)


@pytest.fixture
def native() -> NativeInstallation:
    return fixtures.native.__wrapped__()


def config(
    tmp_path: Path,
    *,
    output_inside: bool = False,
    source_parent: Path | None = None,
    compilation_database: Path | None = None,
    **options: Any,
):
    source = (source_parent or tmp_path) / "source"
    source.mkdir(exist_ok=True)
    (source / "main.cpp").write_text("int value() { return 1; }\n")
    output = source / "output" if output_inside else tmp_path / "store"
    return effective_config(
        source,
        output,
        compilation_database=compilation_database,
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


def assert_input_explanations(
    snapshot: RunSnapshot,
    *,
    changed: bool,
    unavailable: bool,
    causes: tuple[str, ...] = (),
) -> None:
    view = build_snapshot_view(snapshot)
    document = json.loads(render_snapshot_json(view))
    assert (
        document["run"]["input_verification"] == snapshot.manifest["input_verification"]
    )
    limitations = snapshot.manifest["limitations"]
    assert document["run"]["limitations"] == limitations
    html = render_snapshot_html(view)
    for message, present in (
        (INPUT_CHANGED, changed),
        (INPUT_UNAVAILABLE, unavailable),
    ):
        assert (message in limitations) is present
        assert (message in html) is present
    for cause in causes:
        assert any(cause in limitation for limitation in limitations), limitations
        assert escape(cause) in html


def after_native_workers(
    monkeypatch: pytest.MonkeyPatch, action: Callable[[], object]
) -> None:
    """Apply an authored perturbation at the real engine's first postflight read."""
    from cppulse import analysis_execution as engine

    original = engine.discover_sources
    calls = 0

    def discover(root: Path, database=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            action()
        return original(root, database)

    monkeypatch.setattr(engine, "discover_sources", discover)


def test_equal_unavailable_source_observations_do_not_establish_a_binding() -> None:
    from cppulse.analysis_execution import compare_source_observations

    unavailable = {"kind": "unavailable", "path": "main.cpp"}
    assert compare_source_observations([unavailable], [unavailable]) == (
        False,
        ["main.cpp"],
    )


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
    assert_input_explanations(snapshot, changed=False, unavailable=False)
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


@pytest.mark.parametrize(
    ("changed", "unavailable", "execution_verification"),
    [
        pytest.param(False, True, "unavailable", id="unknown-only"),
        pytest.param(True, False, "changed", id="actual-change"),
        pytest.param(True, True, "changed", id="change-and-unknown"),
    ],
)
def test_bounded_input_explanations_keep_changed_and_unavailable_distinct(
    tmp_path: Path,
    native: NativeInstallation,
    monkeypatch: pytest.MonkeyPatch,
    changed: bool,
    unavailable: bool,
    execution_verification: str,
) -> None:
    select_native(monkeypatch, native)
    cfg = config(tmp_path)
    source = cfg.repo / "main.cpp"
    causes = []
    if unavailable:
        source.write_text("int value() { return VALUE; }\n")
        (cfg.repo / "forced.hpp").write_text("#define VALUE 1\n")
        (cfg.repo / "compile_commands.json").write_text(
            json.dumps(
                [
                    {
                        "directory": str(cfg.repo),
                        "file": "main.cpp",
                        "arguments": [
                            "clang++",
                            "-std=c++17",
                            "-include",
                            "forced.hpp",
                            "-c",
                            "main.cpp",
                        ],
                    }
                ]
            )
        )
        causes.append(
            "Input closure is unqualified for hidden/PCH/module/overlay/response context flag: -include"
        )
    if changed:
        after_native_workers(
            monkeypatch, lambda: source.write_text("int after_native() { return 2; }\n")
        )
        causes.append(
            "Source content or discovery inventory changed during native execution."
        )
    result = analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).open_run(result["run_id"])
    summary = private_json(snapshot, "analysis-summary", "analysis_execution_summary")
    assert summary["input_verification"] == execution_verification
    assert result["analysis_status"] == "partial"
    assert snapshot.manifest["status"] == "partial"
    assert (
        result["input_verification"]
        == snapshot.manifest["input_verification"]
        == "unverified"
    )
    bindings = private_json(
        snapshot, "analysis-bindings", "analysis_execution_bindings"
    )
    assert bindings["units"] and all(
        snapshot.read_json(row["receipt_artifact_id"])["status"] == "passed"
        for row in bindings["units"]
    )
    assert_input_explanations(
        snapshot, changed=changed, unavailable=unavailable, causes=tuple(causes)
    )


@pytest.mark.parametrize("renamed", [True, False], ids=["renamed", "unreadable"])
def test_bounded_postflight_source_root_diagnosis(
    tmp_path: Path,
    native: NativeInstallation,
    monkeypatch: pytest.MonkeyPatch,
    renamed: bool,
) -> None:
    select_native(monkeypatch, native)
    parent = tmp_path / "selected"
    parent.mkdir()
    cfg = config(tmp_path, source_parent=parent)
    original = (cfg.repo / "main.cpp").read_bytes()
    moved = parent / "moved-source"
    original_lstat = os.lstat
    mode = parent.stat().st_mode

    def deny_root_lookup(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        if isinstance(path, (str, Path)) and Path(path).is_relative_to(cfg.repo):
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return original_lstat(path, *args, **kwargs)

    def lose_root_access() -> None:
        if renamed:
            cfg.repo.rename(moved)
        elif getattr(os, "geteuid", lambda: 0)() == 0:
            # Privileged test runners can traverse a mode-000 directory.
            monkeypatch.setattr(os, "lstat", deny_root_lookup)
        else:
            parent.chmod(0)

    after_native_workers(monkeypatch, lose_root_access)
    try:
        result = analyze(cfg, report_format="json", timeout=60)
    finally:
        parent.chmod(mode)
        monkeypatch.setattr(os, "lstat", original_lstat)

    assert cfg.repo.exists() == (not renamed)
    assert ((moved if renamed else cfg.repo) / "main.cpp").read_bytes() == original
    store = RunStore(cfg.output)
    snapshot = store.open_run(result["run_id"])
    snapshot.verify()
    assert snapshot.manifest_sha256 == store.resolve_latest_attempt().manifest_sha256
    summary = private_json(snapshot, "analysis-summary", "analysis_execution_summary")
    assert summary["outcomes"]["complete"] == 1
    assert summary["input_verification"] == ("changed" if renamed else "unavailable")
    assert result["analysis_status"] == snapshot.manifest["status"] == "partial"
    assert (
        result["input_verification"]
        == snapshot.manifest["input_verification"]
        == "unverified"
    )
    assert snapshot.read_json("risk_scores")["health_score"]["overall"] is None
    bindings = private_json(
        snapshot, "analysis-bindings", "analysis_execution_bindings"
    )
    (unit,) = bindings["units"]
    receipt = snapshot.read_json(unit["receipt_artifact_id"])
    original_result = private_json(snapshot, unit["result_artifact_id"], "work_result")
    assert receipt == original_result["execution_receipt"]
    assert receipt["status"] == "passed"
    assert receipt["source_digest"] == snapshot.manifest["source"]["digest"]
    cause = (
        "Source content or discovery inventory changed during native execution."
        if renamed
        else "Input root unavailable:"
    )
    assert_input_explanations(
        snapshot, changed=renamed, unavailable=True, causes=(cause,)
    )


def selected_resource_fixture(
    tmp_path: Path, native: NativeInstallation
) -> NativeInstallation:
    resource = tmp_path / "resources"
    (resource / "include").mkdir(parents=True)
    (resource / "include/stddef.h").write_text(
        "// Authored finite builtin resource fixture.\n"
    )
    return NativeInstallation(native.analyzer, resource, native.library_dirs, None)


@pytest.mark.parametrize("disappearing", ["resources", "native"])
def test_bounded_observed_postflight_loss_keeps_specific_change_cause(
    tmp_path: Path,
    native: NativeInstallation,
    monkeypatch: pytest.MonkeyPatch,
    disappearing: str,
) -> None:
    selected = selected_resource_fixture(tmp_path, native)
    if disappearing == "native":
        analyzer = tmp_path / "isolated-analyzer"
        shutil.copy2(native.analyzer, analyzer)
        selected = NativeInstallation(
            analyzer, selected.resource_dir, selected.library_dirs, None
        )
        after_native_workers(monkeypatch, analyzer.unlink)
        cause = "Selected native executable became unavailable after execution."
    else:
        resource = selected.resource_dir
        assert resource is not None
        after_native_workers(monkeypatch, lambda: shutil.rmtree(resource))
        cause = "Selected builtin resources became unavailable during native execution."
    select_native(monkeypatch, selected)
    cfg = config(tmp_path)
    result = analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).open_run(result["run_id"])
    summary = private_json(snapshot, "analysis-summary", "analysis_execution_summary")
    assert summary["input_verification"] == "changed"
    assert summary["outcomes"]["complete"] == 1
    assert result["analysis_status"] == "partial"
    assert snapshot.manifest["input_verification"] == "unverified"
    assert_input_explanations(
        snapshot, changed=True, unavailable=False, causes=(cause,)
    )


@pytest.mark.parametrize("blocked_at", ["inventory", "content-recheck"])
def test_bounded_resource_read_blocked_only_at_publication_is_unavailable(
    tmp_path: Path,
    native: NativeInstallation,
    monkeypatch: pytest.MonkeyPatch,
    blocked_at: str,
) -> None:
    from cppulse import work_units
    from cppulse import analysis_execution as engine

    selected = selected_resource_fixture(tmp_path, native)
    select_native(monkeypatch, selected)
    run_analysis = engine.run_analysis
    cause = "Authored publication-time resource read refusal"
    assert selected.resource_dir is not None
    header = selected.resource_dir / "include/stddef.h"
    original = header.read_bytes()
    original_open = os.open
    opens = 0

    def unreadable(_root: Path):
        raise PermissionError(cause)

    def refuse_content_recheck(path: Any, *args: Any, **kwargs: Any) -> int:
        nonlocal opens
        if path == header:
            opens += 1
            if opens == 2:
                raise PermissionError(cause)
        return original_open(path, *args, **kwargs)

    def run_then_block_resources(*args: Any, **kwargs: Any):
        result = run_analysis(*args, **kwargs)
        assert result.summary["input_verification"] == "verified"
        if blocked_at == "inventory":
            monkeypatch.setattr(work_units, "_resource_files", unreadable)
        else:
            monkeypatch.setattr(os, "open", refuse_content_recheck)
        return result

    monkeypatch.setattr(engine, "run_analysis", run_then_block_resources)
    cfg = config(tmp_path)
    result = analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).open_run(result["run_id"])
    assert result["analysis_status"] == "partial"
    assert snapshot.manifest["input_verification"] == "unverified"
    assert header.read_bytes() == original
    if blocked_at == "content-recheck":
        assert opens >= 2
    assert_input_explanations(
        snapshot, changed=False, unavailable=True, causes=(cause,)
    )


@pytest.mark.parametrize("malformed", [True, False], ids=["changed", "unreadable"])
def test_bounded_postflight_distinguishes_malformed_from_unreadable_database(
    tmp_path: Path,
    native: NativeInstallation,
    monkeypatch: pytest.MonkeyPatch,
    malformed: bool,
) -> None:
    from cppulse import analysis_execution as engine

    select_native(monkeypatch, native)
    database = tmp_path / "external-compilation-database.json"
    database.write_text(
        json.dumps(
            [
                {
                    "directory": str(tmp_path / "source"),
                    "file": "main.cpp",
                    "arguments": ["clang++", "-std=c++17", "-c", "main.cpp"],
                }
            ]
        )
    )
    cfg = config(tmp_path, compilation_database=database)
    saved = database.read_bytes()
    original_open = os.open

    def refuse_read(path: Any, *args: Any, **kwargs: Any) -> int:
        if path == database:
            raise PermissionError("Authored database read refusal")
        return original_open(path, *args, **kwargs)

    read_database = engine._database
    calls = 0

    def change_or_refuse_at_second_read(*args: Any, **kwargs: Any):
        nonlocal calls
        calls += 1
        if calls == 2:
            if malformed:
                database.write_bytes(b"{broken")
            else:
                monkeypatch.setattr(os, "open", refuse_read)
        return read_database(*args, **kwargs)

    monkeypatch.setattr(engine, "_database", change_or_refuse_at_second_read)
    result = analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).open_run(result["run_id"])
    summary = private_json(snapshot, "analysis-summary", "analysis_execution_summary")
    assert calls == 2 and summary["outcomes"]["complete"] == 1
    assert (database.read_bytes() != saved) is malformed
    assert result["analysis_status"] == "partial"
    assert snapshot.manifest["input_verification"] == "unverified"
    cause = (
        "Selected compilation database became invalid during native execution."
        if malformed
        else "Authored database read refusal"
    )
    assert_input_explanations(
        snapshot, changed=malformed, unavailable=not malformed, causes=(cause,)
    )


@pytest.mark.parametrize("blocked", ["dependency", "native"])
def test_bounded_postflight_cannot_read_an_unchanged_input(
    tmp_path: Path,
    native: NativeInstallation,
    monkeypatch: pytest.MonkeyPatch,
    blocked: str,
) -> None:
    from cppulse import analysis_execution as engine

    select_native(monkeypatch, native)
    cfg = config(tmp_path)
    dependency = cfg.repo / "dependency.inc"
    dependency.write_text("#define VALUE 7\n")
    (cfg.repo / "main.cpp").write_text(
        '#include "dependency.inc"\nint value() { return VALUE; }\n'
    )
    target = dependency if blocked == "dependency" else native.analyzer
    original = target.read_bytes()
    hash_artifact = engine.hash_artifact
    cause = f"Authored postflight {blocked} read refusal"

    def refuse_selected(path, artifact_id, *args):
        if Path(path) == target and artifact_id == blocked:
            raise PermissionError(cause)
        return hash_artifact(path, artifact_id, *args)

    after_native_workers(
        monkeypatch,
        lambda: monkeypatch.setattr(engine, "hash_artifact", refuse_selected),
    )
    result = analyze(cfg, report_format="json", timeout=60)
    snapshot = RunStore(cfg.output).open_run(result["run_id"])
    summary = private_json(snapshot, "analysis-summary", "analysis_execution_summary")
    assert target.read_bytes() == original
    assert summary["input_verification"] == "unavailable"
    assert summary["status"] == "partial" and summary["outcomes"]["complete"] == 1
    assert result["analysis_status"] == "partial"
    assert snapshot.manifest["input_verification"] == "unverified"
    assert snapshot.read_json("risk_scores")["health_score"]["overall"] is None
    assert_input_explanations(
        snapshot, changed=False, unavailable=True, causes=(cause,)
    )


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
    assert_input_explanations(
        snapshot,
        changed=True,
        unavailable=False,
        causes=("Source filesystem observations changed before bounded publication",),
    )
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
