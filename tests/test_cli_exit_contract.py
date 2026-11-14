"""Public process exits distinguish incomplete analysis from gate/code failures."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

from cppulse.cli import main
from cppulse.config import effective_config
import test_pipeline_snapshot_import as import_fixtures
from test_pipeline_failures import stub_native

bundle = import_fixtures.bundle


@pytest.mark.parametrize(
    "scope_state, errors, health_status, expected",
    [
        ("analyzed", 0, "scored", "completed"),
        ("partial", 1, "partial", "partial"),
        ("skipped", 0, "partial", "partial"),
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
    if scope_state is None:
        (source / "sample.cpp").unlink()
        findings["metadata"]["analysis"]["files"] = []
        findings["metadata"].update(file_count=0, total_loc=0)
    else:
        entry = findings["metadata"]["analysis"]["files"][0]
        entry.update(status=scope_state, error_count=errors)
    native_findings.write_text(json.dumps(findings), encoding="utf-8")
    stub_native(monkeypatch, findings=native_findings)

    result = pipeline.analyze(effective_config(source, output), report_format="json")

    risk = json.loads((output / "risk_scores.json").read_bytes())
    assert risk["health_score"]["status"] == health_status
    assert result["analysis_status"] == expected


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
