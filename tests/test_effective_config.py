"""Exercise config precedence and data-only behavior before orchestration."""

from pathlib import Path
from itertools import combinations

import pytest
from cppulse.config import CONFIG_NAMES, effective_config, initialize
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


@pytest.mark.parametrize("names", list(combinations(CONFIG_NAMES, 2)))
def test_multiple_discovered_configs_require_explicit_selection(
    tmp_path: Path, names: tuple[str, str]
) -> None:
    """No extension or directory order may silently choose project requirements."""
    for name in names:
        (tmp_path / name).write_text("{}", encoding="utf-8")

    with pytest.raises(ContractError, match="[Aa]mbiguous") as raised:
        effective_config(tmp_path, tmp_path / "out")

    assert all(name in str(raised.value) for name in names)
    assert "--config" in str(raised.value)


def test_explicit_config_disambiguates_without_loading_other_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit invocation-relative selection overrides discovery, not file order."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".cppulserc.yml").write_text("invalid: unsupported", encoding="utf-8")
    selected = repo / ".cppulserc.json"
    selected.write_text('{"profile":"safety-critical"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    config = effective_config(
        Path("repo"), Path("out"), config=Path("repo/.cppulserc.json")
    )

    assert config.config_path == selected
    assert config.settings["profile"] == "safety-critical"


def test_effective_config_reports_the_native_file_budget_default(
    tmp_path: Path,
) -> None:
    """Inspection must show the limit actually forwarded to native analysis."""
    selected = effective_config(tmp_path, tmp_path / "out")

    assert selected.settings["max_file_bytes"] == 16 * 1024 * 1024


def test_explicit_file_budget_overrides_the_shared_default(tmp_path: Path) -> None:
    """Large-header users can select an adequate bounded budget in project data."""
    (tmp_path / ".cppulserc.json").write_text(
        '{"max_file_bytes":67108864}', encoding="utf-8"
    )

    selected = effective_config(tmp_path, tmp_path / "out")

    assert selected.settings["max_file_bytes"] == 64 * 1024 * 1024


@pytest.mark.parametrize(
    "filename, content",
    [
        (".cppulserc.json", '{"profile":"safety-critical","profile":"default"}'),
        (
            ".cppulserc.json",
            '{"rules":{"CPP-MEM-001":{"enabled":true,"enabled":false}}}',
        ),
        (".cppulserc.yml", "profile: safety-critical\nprofile: default\n"),
        (
            ".cppulserc.yml",
            "rules:\n  CPP-MEM-001:\n    enabled: true\n    enabled: false\n",
        ),
    ],
)
def test_duplicate_configuration_keys_cannot_override_requirements(
    tmp_path: Path, filename: str, content: str
) -> None:
    """Root and nested duplicates must not silently disable selected checks."""
    (tmp_path / filename).write_text(content, encoding="utf-8")

    with pytest.raises(ContractError, match="[Dd]uplicate"):
        effective_config(tmp_path, tmp_path / "out")
