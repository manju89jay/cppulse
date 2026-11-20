"""Public portfolio reads and explicit local ticks share the same pinned engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cppulse.cli import main
from test_portfolio import settings


def test_public_portfolio_retains_pins_and_no_cross_project_health(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = settings(tmp_path)
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(config))
    assert (
        main(
            [
                "portfolio",
                "report",
                "--config",
                str(path),
                "--at",
                "2026-11-16T10:00:00Z",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["aggregate_health"] is None
    assert report["selection"] == "historical-pinned"
    assert report["current_source_verified"] is False
    assert [(row["run_id"], row["manifest_sha256"]) for row in report["projects"]] == [
        (row["run_id"], row["manifest_sha256"]) for row in config["projects"]
    ]


def test_local_tick_is_idempotent_and_never_claims_policy_acceptance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = settings(tmp_path, schedules=True)
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(config))
    output = tmp_path / "reports"
    output.mkdir()
    args = [
        "portfolio",
        "tick",
        "--config",
        str(path),
        "--output-root",
        str(output),
        "--at",
        "2026-11-16T15:00:00Z",
    ]
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["delivery_kind"] == "local-files-only"
    assert first["policy_acceptance"] == "not_assessed"
    assert first["outcomes"]
    files = {p.name: p.read_bytes() for p in output.iterdir()}
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["outcomes"] == []
    assert {p.name: p.read_bytes() for p in output.iterdir()} == files


def test_unresolved_exhausted_local_delivery_remains_an_operational_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import cppulse.portfolio as portfolio

    config = settings(tmp_path, schedules=True)
    # Select one intended local date: the shared helper otherwise catches up
    # yesterday and today, correctly yielding two independent exhausted jobs.
    config["schedules"][0].update(max_attempts=1, lookback_days=1)
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(config))
    output = tmp_path / "reports"
    output.mkdir()

    def fail(*args: object, **kwargs: object) -> object:
        raise OSError("Controlled local delivery fault")

    monkeypatch.setattr(portfolio, "build_portfolio", fail)
    args = [
        "portfolio",
        "tick",
        "--config",
        str(path),
        "--output-root",
        str(output),
        "--at",
        "2026-11-16T15:00:00Z",
    ]
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["active_job_counts"]["exhausted"] == 1
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["outcomes"] == []


def test_empty_replay_clock_is_not_silently_replaced_with_now(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(settings(tmp_path)))
    assert main(["portfolio", "report", "--config", str(path), "--at", ""]) == 2
    assert capsys.readouterr().out == ""


def test_relative_tick_directory_is_resolved_without_following_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(settings(tmp_path, schedules=True)))
    (tmp_path / "reports").mkdir()
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "portfolio",
                "tick",
                "--config",
                str(path),
                "--output-root",
                "reports",
                "--at",
                "2026-11-16T15:00:00Z",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["delivery_kind"] == "local-files-only"
