"""Exercise config precedence and data-only behavior before orchestration."""

from pathlib import Path

import pytest
from cppulse.config import effective_config, initialize
from cppulse.errors import ContractError


def test_profile_precedence_and_invocation_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo with space"
    repo.mkdir()
    (repo / ".cppulserc.yml").write_text(
        "profile: safety-critical\nexclude_paths:\n  - 'vendor/**'\n"
    )
    monkeypatch.chdir(tmp_path)
    selected = effective_config(Path(repo.name), Path("out"))
    assert selected.settings["profile"] == "safety-critical"
    assert selected.profile_source == "config"
    assert selected.output == tmp_path / "out"
    override = effective_config(repo, Path("out"), profile="default")
    assert override.settings["profile"] == "default"
    assert override.profile_source == "command"
    assert override.settings["exclude_paths"] == ["vendor/**"]


def test_init_refuses_overwrite(tmp_path: Path) -> None:
    path = initialize(tmp_path)
    before = path.read_bytes()
    with pytest.raises(ContractError):
        initialize(tmp_path)
    assert path.read_bytes() == before


def test_config_never_executes_yaml_tags(tmp_path: Path) -> None:
    (tmp_path / ".cppulserc.yml").write_text(
        "!!python/object/apply:os.system ['touch executed']"
    )
    with pytest.raises(ContractError):
        effective_config(tmp_path, tmp_path / "out")
    assert not (tmp_path / "executed").exists()


def test_unknown_setting_is_actionable(tmp_path: Path) -> None:
    (tmp_path / ".cppulserc.json").write_text('{"execute":"build"}')
    with pytest.raises(ContractError, match="Additional properties"):
        effective_config(tmp_path, tmp_path / "out")


def test_unregistered_rule_is_not_silently_ignored(tmp_path: Path) -> None:
    (tmp_path / ".cppulserc.json").write_text(
        '{"rules":{"CPP-CX-999":{"enabled":false}}}'
    )
    with pytest.raises(ContractError, match="Unknown rule IDs: CPP-CX-999"):
        effective_config(tmp_path, tmp_path / "out")


def test_threshold_must_fit_native_integer(tmp_path: Path) -> None:
    (tmp_path / ".cppulserc.json").write_text(
        '{"rules":{"CPP-CX-001":{"warning_threshold":2147483648}}}'
    )
    with pytest.raises(ContractError, match="maximum"):
        effective_config(tmp_path, tmp_path / "out")
