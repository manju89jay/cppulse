"""Public process exits distinguish incomplete analysis from gate/code failures."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

from cppulse.cli import main
from cppulse.config import effective_config
from cppulse.run_store import RunStore
from cppulse.tooling import load_rule_registry
import test_pipeline_snapshot_import as import_fixtures
from test_pipeline_failures import stub_native

bundle = import_fixtures.bundle


@pytest.mark.parametrize(
    "scope_state, errors, health_status, expected",
    [
        ("analyzed", 0, "partial", "completed"),
        ("partial", 1, "partial", "partial"),
        ("failed", 0, "partial", "partial"),
        ("skipped", 0, "partial", "partial"),
        ("excluded", 0, "no_data", "partial"),
        (None, 0, "no_data", "partial"),
    ],
)
def test_pipeline_status_describes_analysis_instead_of_successful_archival(
    bundle: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    scope_state: str | None,
    errors: int,
    health_status: str,
    expected: str,
) -> None:
    """Real prediction/import retains its scope status across the public boundary."""
    import cppulse.pipeline as pipeline

    flat, source, output = bundle
    native_findings = flat / "findings.json"
    findings = json.loads(native_findings.read_bytes())
    analysis = findings["metadata"]["analysis"]
    analysis["parser"] = {"name": "libclang", "version": "test fixture"}
    analysis["enabled_rules"] = [rule["id"] for rule in load_rule_registry()["rules"]]
    if scope_state is None:
        (source / "sample.cpp").unlink()
        analysis["files"] = []
        findings["metadata"].update(file_count=0, total_loc=0)
    else:
        analysis["files"][0].update(
            status=scope_state,
            error_count=errors,
            parse_arguments=["-std=c++17"],
            working_directory=str(source),
        )
    native_findings.write_text(json.dumps(findings), encoding="utf-8")
    stub_native(monkeypatch, findings=native_findings)

    result = pipeline.analyze(effective_config(source, output), report_format="json")

    risk = json.loads((output / "risk_scores.json").read_bytes())
    assert risk["health_score"]["status"] == health_status
    assert risk["health_score"]["overall"] is None
    assert result["analysis_status"] == expected
    snapshot = RunStore.open_existing(output).open_run(
        result["run_id"], manifest_sha256=result["manifest_sha256"]
    )
    assert snapshot.manifest["input_verification"] == "unverified"
    assert result["input_verification"] == "unverified"
    assert snapshot.manifest["contexts"] == []
    assert snapshot.read_json("normalized-risk")["health_score"]["overall"] is None


@pytest.mark.parametrize(
    "gap",
    [
        "fallback",
        "inferred",
        "none",
        "unobserved",
        "missing-rule",
        "count",
        "missing-report",
    ],
)
def test_legacy_requires_declared_context_and_completed_stages(
    bundle: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    gap: str,
) -> None:
    """An archive can be retained even when a required analysis stage is missing."""
    import cppulse.pipeline as pipeline

    flat, source, output = bundle
    database = source / "compile_commands.json"
    database.write_text("[]", encoding="utf-8")
    native_findings = flat / "findings.json"
    findings = json.loads(native_findings.read_bytes())
    metadata = findings["metadata"]
    analysis = metadata["analysis"]
    analysis["parser"] = {"name": "libclang", "version": "test fixture"}
    analysis["enabled_rules"] = [rule["id"] for rule in load_rule_registry()["rules"]]
    row = analysis["files"][0]
    row.update(
        compile_context=gap if gap in {"fallback", "inferred", "none"} else "database",
        parse_arguments=["-std=c++17"],
        working_directory=str(source),
    )
    if gap == "unobserved":
        row.pop("parse_arguments")
    elif gap == "missing-rule":
        analysis["enabled_rules"].remove("CPP-MOD-001")
    elif gap == "count":
        metadata["file_count"] = 0
    elif gap == "missing-report":
        monkeypatch.setattr(pipeline, "generate_report", lambda *args: {})
    native_findings.write_text(json.dumps(findings), encoding="utf-8")
    stub_native(monkeypatch, findings=native_findings)

    arguments = [
        "analyze",
        "--repo",
        str(source),
        "--output",
        str(output),
        "--compilation-database",
        str(database),
        "--format",
        "json",
    ]
    assert main(arguments) == 3
    result = json.loads(capsys.readouterr().out)
    assert result["analysis_status"] == "partial"
    assert result["input_verification"] == "unverified"
    risk = json.loads((output / "risk_scores.json").read_bytes())
    assert risk["health_score"]["overall"] is None
    if gap == "missing-report":
        assert result["report"] is None


@pytest.mark.parametrize("command", ["analyze", "watch"])
@pytest.mark.parametrize("status, expected", [("completed", 0), ("partial", 3)])
def test_analysis_and_finite_watch_use_analysis_scope_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
    status: str,
    expected: int,
) -> None:
    """Archive completion alone cannot make an incomplete source analysis pass."""
    import cppulse.pipeline as pipeline

    result = {
        "operation": "archive-import",
        "run_id": "retained",
        "analysis_status": status,
    }
    monkeypatch.setattr(pipeline, "analyze", lambda *args, **kwargs: result)
    arguments = [command, "--repo", str(tmp_path), "--format", "json"]
    if command == "watch":
        arguments.extend(["--iterations", "1"])

    assert main(arguments) == expected
    assert json.loads(capsys.readouterr().out) == result


@pytest.mark.parametrize(
    "failure",
    [
        OSError("cannot create output"),
        RuntimeError("native process could not complete"),
        subprocess.TimeoutExpired("synthetic-native", 1),
        ImportError("optional runtime unavailable", name="synthetic_pdf"),
    ],
)
def test_analysis_operational_failure_is_not_a_known_failed_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: Exception,
) -> None:
    """Exit 1 is reserved for a policy/finding gate with an observed failure."""
    import cppulse.pipeline as pipeline

    def fail(*args: Any, **kwargs: Any) -> None:
        raise failure

    monkeypatch.setattr(pipeline, "analyze", fail)

    assert main(["analyze", "--repo", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cppulse:" in captured.err


def test_collection_operational_failure_is_not_missing_verification_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A runner startup error without usable results is an operational error."""
    import cppulse.workflows as workflows

    request = tmp_path / "request.json"
    request.write_text("{}", encoding="utf-8")

    def unavailable(*args: Any, **kwargs: Any) -> None:
        raise OSError("cannot open collection output")

    monkeypatch.setattr(workflows, "collect_request", unavailable)
    code = main(
        [
            "collect",
            "--request",
            str(request),
            "--workspace",
            str(tmp_path),
            "--store",
            str(tmp_path / "store"),
        ]
    )

    assert code == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "invalid"
    assert result["exit_code"] == 2
    assert result["error"]["code"] == "IO_ERROR"


def test_analysis_keyboard_interrupt_preserves_cancellation_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Operational-error normalization must never turn SIGINT into exit 2."""
    import cppulse.pipeline as pipeline

    def cancel(*args: Any, **kwargs: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "analyze", cancel)

    assert main(["analyze", "--repo", str(tmp_path)]) == 130
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cancelled" in captured.err


def test_doctor_missing_required_native_component_is_operational_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing required installation components are not a failed code gate."""
    import cppulse.cli as cli

    monkeypatch.setattr(cli, "doctor", lambda: {"native": {"available": False}})

    assert main(["doctor"]) == 2
    assert json.loads(capsys.readouterr().out)["native"]["available"] is False
