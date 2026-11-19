"""Actual subprocess adapter evidence; no shared CLI mutation."""

from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from test_branch_delivery import (
    history as _history,
    config,
    git,
)  # real authored Git fixture
from cppulse.branch_delivery_cli import main


@pytest.fixture
def history(tmp_path):
    return _history.__wrapped__(tmp_path)


def invoke(
    repo: Path, configuration: Path, output: Path
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "cppulse.branch_delivery_cli",
            "--repo",
            str(repo),
            "--config",
            str(configuration),
            "--output",
            str(output),
        ],
        env={**os.environ, "PYTHONPATH": str(Path("python").absolute())},
        text=True,
        capture_output=True,
        timeout=30,
    )


def fixture_inputs(history, tmp_path):
    repo, ids = history
    cfg = tmp_path / "configuration.json"
    cfg.write_text(json.dumps(config(ids)))
    return repo, cfg, tmp_path / "output"


def test_actual_cli_retains_replayable_graph_and_original_bytes(history, tmp_path):
    from cppulse.branch_delivery import validate_report

    repo, cfg, output = fixture_inputs(history, tmp_path)
    before = git(repo, "rev-parse", "HEAD")
    result = invoke(repo, cfg, output)
    assert result.returncode == 0, result.stderr
    assert (output / "config.original.json").read_bytes() == cfg.read_bytes()
    receipt = json.loads((output / "outcome.json").read_bytes())
    assert receipt["exit_code"] == 0
    assert "no provider" in receipt["meaning"]
    validate_report(
        json.loads((output / "report.json").read_bytes()),
        config=json.loads((output / "config.json").read_bytes()),
        capture=json.loads((output / "capture.json").read_bytes()),
    )
    assert git(repo, "rev-parse", "HEAD") == before


def test_actual_cli_partial_retained_and_existing_output_never_replaced(
    history, tmp_path
):
    repo, cfg, output = fixture_inputs(history, tmp_path)
    doc = json.loads(cfg.read_text())
    doc["refs"][0]["expected_tip"] = "0" * 40
    cfg.write_text(json.dumps(doc))
    assert invoke(repo, cfg, output).returncode == 3
    original = (output / "report.json").read_bytes()
    assert invoke(repo, cfg, output).returncode == 2
    assert (output / "report.json").read_bytes() == original


@pytest.mark.parametrize("raw", ['{"id":1,"id":2}', '{"id":NaN}', "[", "{}"])
def test_invalid_config_before_any_git_or_output(history, tmp_path, monkeypatch, raw):
    repo, cfg, output = fixture_inputs(history, tmp_path)
    cfg.write_text(raw)
    monkeypatch.setattr(
        "cppulse.branch_delivery_cli.collect_branch_graph",
        lambda *args: pytest.fail("Git before validation"),
    )
    assert (
        main(["--repo", str(repo), "--config", str(cfg), "--output", str(output)]) == 2
    )
    assert not output.exists()


@pytest.mark.parametrize("kind", ["fifo", "symlink", "oversize"])
def test_configuration_boundaries_are_nonblocking(history, tmp_path, kind):
    repo, cfg, output = fixture_inputs(history, tmp_path)
    selected = tmp_path / "input"
    if kind == "fifo":
        os.mkfifo(selected)
    elif kind == "symlink":
        selected.symlink_to(cfg)
    else:
        selected.write_bytes(b" " * (512 * 1024 + 1))
    assert invoke(repo, selected, output).returncode == 2
    assert not output.exists()


def test_source_and_linked_metadata_output_are_rejected(history, tmp_path):
    repo, cfg, _ = fixture_inputs(history, tmp_path)
    assert invoke(repo, cfg, repo / "result").returncode == 2
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-b", "linked-cli", str(linked))
    metadata = Path((linked / ".git").read_text().strip()[8:])
    assert invoke(linked, cfg, metadata / "result").returncode == 2
    assert not (metadata / "result").exists()


def test_interrupt_retains_diagnostics_and_input(history, tmp_path, monkeypatch):
    repo, cfg, output = fixture_inputs(history, tmp_path)

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr("cppulse.branch_delivery_cli.collect_branch_graph", interrupt)
    assert (
        main(["--repo", str(repo), "--config", str(cfg), "--output", str(output)])
        == 130
    )
    assert (output / "config.original.json").exists()
    assert json.loads((output / "error.json").read_text())["exit_code"] == 130


def test_unavailable_producer_has_retained_outcome(history, tmp_path, monkeypatch):
    repo, cfg, output = fixture_inputs(history, tmp_path)
    monkeypatch.setenv("GIT_DIR", "0")
    result = invoke(repo, cfg, output)
    assert result.returncode == 3
    assert (
        json.loads((output / "outcome.json").read_text())["graph_status"]
        == "unavailable"
    )
    assert json.loads((output / "capture.json").read_text())["commands"] == []


def test_symlink_output_ancestor_is_denied(history, tmp_path):
    repo, cfg, output = fixture_inputs(history, tmp_path)
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    assert invoke(repo, cfg, alias / "result").returncode == 2
    assert not (actual / "result").exists()


def test_runtime_failure_retains_inputs_and_concrete_diagnostic(
    history, tmp_path, monkeypatch
):
    repo, cfg, output = fixture_inputs(history, tmp_path)

    def failure(*args):
        raise OSError("controlled read failure")

    monkeypatch.setattr("cppulse.branch_delivery_cli.collect_branch_graph", failure)
    assert (
        main(["--repo", str(repo), "--config", str(cfg), "--output", str(output)]) == 2
    )
    assert (output / "config.original.json").read_bytes() == cfg.read_bytes()
    assert (
        json.loads((output / "error.json").read_text())["message"]
        == "controlled read failure"
    )
