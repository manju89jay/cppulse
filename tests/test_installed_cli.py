"""Verify installed-dispatch semantics independently of checkout orchestration."""

from __future__ import annotations

import json
from pathlib import Path
import zipfile

import pytest
import jsonschema

from cppulse.cli import diagnostic_bundle, main
from cppulse.config import effective_config
from cppulse.pipeline import analyze, generate_report
from cppulse.run_store import RunStore


def test_init_config_machine_output_does_not_run_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "CMakeLists.txt").write_text("execute_process(COMMAND touch executed)")
    assert main(["init", "--repo", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["config"].endswith(".cppulserc.json")
    assert (
        main(["config", "--repo", str(tmp_path), "--profile", "safety-critical"]) == 0
    )
    assert (
        json.loads(capsys.readouterr().out)["settings"]["profile"] == "safety-critical"
    )
    assert not (tmp_path / "executed").exists()


def test_missing_native_publishes_incomplete_attempt_and_report_refuses_old_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    output = tmp_path / "out"
    output.mkdir()
    (output / "risk_scores.json").write_text('{"health_score":{"overall":100}}')
    monkeypatch.setenv("CPPULSE_ANALYZER", str(tmp_path / "missing"))
    with pytest.raises(ValueError):
        analyze(effective_config(repo, output))
    latest = RunStore(output).resolve_latest_attempt()
    assert latest.manifest["status"] == "partial"
    assert RunStore.open_existing(output).resolve_heads()[1] is None
    with pytest.raises(RuntimeError, match="Latest attempt.*partial"):
        generate_report(output, "html")


def test_diagnostics_default_excludes_paths_environment_and_raw_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.cli as cli

    monkeypatch.setenv("MY_PRIVATE_TOKEN", "do-not-copy")
    monkeypatch.setattr(
        cli,
        "doctor",
        lambda: {
            "cppulse": "0.2.0.dev0",
            "native": {
                "available": False,
                "path": "/private/home",
                "error": "secret do-not-copy",
                "error_code": "MISSING",
            },
            "optional": {},
        },
    )
    bundle = diagnostic_bundle(tmp_path / "diagnostics.zip")
    with zipfile.ZipFile(bundle) as archive:
        assert archive.namelist() == ["diagnostics.json"]
        content = archive.read("diagnostics.json").decode()
        assert "do-not-copy" not in content
        assert "/private/home" not in content
        assert "MISSING" in content
    with pytest.raises(FileExistsError):
        diagnostic_bundle(bundle)


def test_explicit_bad_config_returns_invalid_input_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"profile":"invented"}')
    assert main(["config", "--repo", str(tmp_path), "--config", str(bad)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Invalid project configuration" in captured.err


def test_producer_schema_error_is_concise_invalid_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import cppulse.pipeline as pipeline

    def invalid(*args: object, **kwargs: object) -> None:
        raise jsonschema.ValidationError("missing findings summary")

    monkeypatch.setattr(pipeline, "analyze", invalid)
    assert main(["analyze", "--repo", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "cppulse: invalid contract: missing findings summary"
