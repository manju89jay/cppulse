"""Execution budgets have explicit precedence and never enter native rule config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cppulse.config import effective_config
from cppulse.errors import ContractError


def test_project_execution_and_explicit_override_are_inspectable(
    tmp_path: Path,
) -> None:
    (tmp_path / ".cppulserc.json").write_text(
        json.dumps(
            {
                "execution": {
                    "mode": "bounded",
                    "jobs": 2,
                    "wall_seconds": 12,
                    "work_directory": "../work-state",
                }
            }
        )
    )
    config = effective_config(tmp_path, tmp_path / "output", execution={"jobs": 3})
    assert config.execution["jobs"] == 3
    assert config.execution["wall_seconds"] == 12
    assert config.execution["mode"] == "bounded"
    assert config.execution["work_directory"] == str(tmp_path.parent / "work-state")
    assert "execution" not in config.settings
    assert config.as_dict()["execution"] == config.execution


@pytest.mark.parametrize(
    "value",
    [
        {"jobs": 0},
        {"jobs": True},
        {"wall_seconds": float("inf")},
        {"address_space_bytes": -1},
        {"mode": "pretend"},
        {"resume": "yes"},
        {"unrecognized": 1},
    ],
)
def test_invalid_execution_options_are_rejected_before_tools(
    tmp_path: Path, value: dict
) -> None:
    with pytest.raises(ContractError):
        effective_config(tmp_path, tmp_path / "output", execution=value)


def test_resume_needs_an_explicit_retained_work_directory(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="work_directory"):
        effective_config(
            tmp_path, tmp_path / "output", execution={"mode": "bounded", "resume": True}
        )


def test_execution_default_preserves_legacy_until_bounded_gate(tmp_path: Path) -> None:
    config = effective_config(tmp_path, tmp_path / "output")
    assert config.execution["mode"] == "legacy"
    assert config.execution["jobs"] == 1
    assert config.execution["resume"] is False


def test_public_config_reports_execution_flags_without_native_rules_leak(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from cppulse.cli import main

    code = main(
        [
            "config",
            "--repo",
            str(tmp_path),
            "--jobs",
            "2",
            "--memory-limit-mib",
            "768",
            "--unit-timeout",
            "15",
        ]
    )
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["execution"]["mode"] == "bounded"
    assert result["execution"]["jobs"] == 2
    assert result["execution"]["address_space_bytes"] == 768 * 1024**2
    assert result["execution"]["wall_seconds"] == 15
    assert "execution" not in result["settings"]


def test_public_config_can_disable_stored_resume_explicitly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from cppulse.cli import main

    (tmp_path / ".cppulserc.json").write_text(
        json.dumps(
            {
                "execution": {
                    "mode": "bounded",
                    "resume": True,
                    "work_directory": "../state",
                }
            }
        )
    )
    assert main(["config", "--repo", str(tmp_path), "--no-resume"]) == 0
    assert json.loads(capsys.readouterr().out)["execution"]["resume"] is False


def test_explicit_legacy_mode_can_override_a_bounded_project(tmp_path: Path) -> None:
    (tmp_path / ".cppulserc.json").write_text(
        json.dumps({"execution": {"mode": "bounded", "jobs": 2}})
    )
    config = effective_config(tmp_path, tmp_path / "out", execution={"mode": "legacy"})
    assert config.execution["mode"] == "legacy"
    assert (
        config.execution["jobs"] == 2
    )  # recorded, inapplicable in explicit legacy mode


def test_contradictory_explicit_legacy_budget_is_actionable(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="bounded"):
        effective_config(
            tmp_path, tmp_path / "out", execution={"mode": "legacy", "jobs": 2}
        )
