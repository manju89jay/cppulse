"""Public finite history configuration preserves optional tooling boundaries."""

from pathlib import Path
import json
import pytest
from cppulse.config import effective_config, default_history
from cppulse.errors import ContractError
from cppulse.history_boundary import mine_optional_history


def test_history_is_separate_and_paths_follow_project_precedence(
    tmp_path: Path,
) -> None:
    (tmp_path / ".cppulserc.json").write_text(
        json.dumps(
            {"history": {"enabled": False, "cache_dir": "cache", "max_commits": 7}}
        )
    )
    value = effective_config(tmp_path, tmp_path / "out")
    assert "history" not in value.settings
    assert value.history["enabled"] is False
    assert value.history["cache_dir"] == str(tmp_path / "cache")
    assert value.history["max_commits"] == 7
    explicit = effective_config(tmp_path, tmp_path / "out", history={"enabled": True})
    assert explicit.history["enabled"] is True
    assert explicit.history["max_commits"] == 7


@pytest.mark.parametrize(
    "options",
    [
        {"max_commits": 0},
        {"max_record_bytes": 100},
        {"max_cache_bytes": 0},
        {"timeout_seconds": float("nan")},
        {"szz_max_fix_commits": -1},
        {"behavior_cutoff": "2026-11-16T00:00:00Z"},
        {"enabled": "no"},
        {"invented": 1},
    ],
)
def test_invalid_history_rejected_before_execution(
    tmp_path: Path, options: dict
) -> None:
    with pytest.raises(ContractError):
        effective_config(tmp_path, tmp_path / "out", history=options)


def test_disabled_history_does_not_probe_or_import_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object) -> None:
        raise AssertionError("Disabled history must not probe Git tooling")

    monkeypatch.setattr("cppulse.history_boundary.shutil.which", forbidden)
    monkeypatch.setattr("cppulse.history_boundary.importlib.util.find_spec", forbidden)
    options = {**default_history(), "enabled": False}
    assert mine_optional_history(tmp_path, tmp_path, options=options) == 0
    data = json.loads((tmp_path / "git_metrics.json").read_text())
    assert data["metadata"]["history_status"] == "unavailable"
    assert data["file_metrics"] == []
    assert "explicitly disabled" in data["metadata"]["limitations"][0]


def test_available_boundary_forwards_explicit_budgets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.git_miner.main as miner

    calls = []

    def capture(*args: object, **kwargs: object) -> int:
        calls.append((args, kwargs))
        return 2

    monkeypatch.setattr("cppulse.history_boundary.shutil.which", lambda _: "/git")
    monkeypatch.setattr(miner, "run", capture)
    options = {
        **default_history(),
        "cache_dir": str(tmp_path / "cache"),
        "max_commits": 8,
    }
    assert mine_optional_history(tmp_path, tmp_path, options=options) == 2
    assert calls[0][1]["history_options"]["max_commits"] == 8
    assert calls[0][1]["history_options"]["cache_dir"] == str(tmp_path / "cache")
    assert calls[0][1]["szz_max_fix_commits"] == 500
