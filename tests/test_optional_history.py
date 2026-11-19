"""Static analysis retains explicit missing-history facts without optional Git."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cppulse.history_boundary import mine_optional_history
from cppulse.contracts import validate


def test_missing_git_runtime_writes_valid_unavailable_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cppulse.history_boundary.shutil.which", lambda _: None)
    repo = tmp_path / "source"
    repo.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    assert mine_optional_history(repo, output) == 0
    data = json.loads((output / "git_metrics.json").read_text())
    validate("git_metrics", data, version="prototype_v1")
    assert data["metadata"]["history_status"] == "unavailable"
    assert data["metadata"]["total_commits"] == 0
    assert data["file_metrics"] == []
    assert data["knowledge_silos"] == []
    assert "Git executable" in data["metadata"]["limitations"][0]


def test_missing_gitpython_is_explicit_and_does_not_import_miner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cppulse.history_boundary.shutil.which", lambda _: "/git")
    monkeypatch.setattr(
        "cppulse.history_boundary.importlib.util.find_spec", lambda _: None
    )
    assert mine_optional_history(tmp_path, tmp_path) == 0
    data = json.loads((tmp_path / "git_metrics.json").read_text())
    assert "GitPython" in data["metadata"]["limitations"][0]


def test_available_history_preserves_miner_operational_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.git_miner.main as miner

    monkeypatch.setattr("cppulse.history_boundary.shutil.which", lambda _: "/git")
    monkeypatch.setattr(miner, "run", lambda *_: 2)
    assert mine_optional_history(tmp_path, tmp_path) == 2


@pytest.mark.parametrize("disabled", [True, False])
def test_unavailable_history_refuses_mixed_retained_sidecars_before_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, disabled: bool
) -> None:
    from cppulse.errors import ContractError
    from cppulse.config import default_history

    monkeypatch.setattr("cppulse.history_boundary.shutil.which", lambda _: None)
    original = b"previous metrics must remain"
    (tmp_path / "git_metrics.json").write_bytes(original)
    (tmp_path / "git_behavior.json").write_bytes(b"previous rich facts")
    options = {**default_history(), "enabled": False} if disabled else None
    with pytest.raises(ContractError, match="fresh output"):
        mine_optional_history(tmp_path, tmp_path, options=options)
    assert (tmp_path / "git_metrics.json").read_bytes() == original
    assert (tmp_path / "git_behavior.json").read_bytes() == b"previous rich facts"
