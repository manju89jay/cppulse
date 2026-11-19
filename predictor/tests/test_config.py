"""Tests for predictor config file loading (_load_profile_from_config)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.main import _load_profile_from_config
from cppulse.errors import ContractError


@pytest.mark.parametrize(
    "value",
    [
        "safety-critical # selected scoring profile",
        "'safety-critical' # quoted YAML value",
        '"safety-critical" # double-quoted YAML value',
    ],
)
def test_profile_with_yaml_inline_comment(tmp_path: Path, value: str) -> None:
    """A valid commented YAML profile must not silently select default scoring."""
    path = tmp_path / ".cppulserc.yml"
    path.write_text(f"profile: {value}\n", encoding="utf-8")
    assert _load_profile_from_config(path) == "safety-critical"


@pytest.fixture()
def tmp_config(tmp_path: Path):
    """Factory for creating temporary config files."""

    def _write(filename: str, content: str) -> Path:
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        return p

    return _write


class TestLoadProfileFromYaml:
    """Test YAML config loading (with and without PyYAML)."""

    def test_reads_default_profile(self, tmp_config):
        p = tmp_config(".cppulserc.yml", "profile: default\n")
        assert _load_profile_from_config(p) == "default"

    def test_reads_safety_critical_profile(self, tmp_config):
        p = tmp_config(".cppulserc.yml", "profile: safety-critical\n")
        assert _load_profile_from_config(p) == "safety-critical"

    def test_missing_profile_returns_default(self, tmp_config):
        p = tmp_config(".cppulserc.yml", "exclude_paths:\n  - vendor/**\n")
        assert _load_profile_from_config(p) == "default"

    def test_unknown_profile_is_not_silently_defaulted(self, tmp_config):
        p = tmp_config(".cppulserc.yml", "profile: unknown-profile\n")
        with pytest.raises(ContractError, match="profile"):
            _load_profile_from_config(p)

    def test_full_config_reads_profile(self, tmp_config):
        content = (
            "profile: safety-critical\n"
            "exclude_paths:\n"
            "  - vendor/**\n"
            "rules:\n"
            "  CPP-CX-001:\n"
            "    warning_threshold: 20\n"
        )
        p = tmp_config(".cppulserc.yml", content)
        assert _load_profile_from_config(p) == "safety-critical"


class TestLoadProfileFromJson:
    """Test JSON config loading."""

    def test_reads_default_profile(self, tmp_config):
        p = tmp_config(".cppulserc.json", json.dumps({"profile": "default"}))
        assert _load_profile_from_config(p) == "default"

    def test_reads_safety_critical_profile(self, tmp_config):
        p = tmp_config(".cppulserc.json", json.dumps({"profile": "safety-critical"}))
        assert _load_profile_from_config(p) == "safety-critical"

    def test_missing_profile_returns_default(self, tmp_config):
        p = tmp_config(".cppulserc.json", json.dumps({"exclude_paths": ["vendor/**"]}))
        assert _load_profile_from_config(p) == "default"


class TestLoadProfileEdgeCases:
    """Edge cases for config loading."""

    def test_explicit_nonexistent_file_is_not_silently_defaulted(self, tmp_path: Path):
        p = tmp_path / "nonexistent.yml"
        with pytest.raises(FileNotFoundError):
            _load_profile_from_config(p)

    def test_empty_yaml_file_preserves_default_configuration(self, tmp_config):
        p = tmp_config(".cppulserc.yml", "")
        assert _load_profile_from_config(p) == "default"

    def test_quoted_profile_value(self, tmp_config):
        p = tmp_config(".cppulserc.yml", "profile: 'safety-critical'\n")
        assert _load_profile_from_config(p) == "safety-critical"


@pytest.mark.parametrize("text", ["", "  \n# default settings\n", "---\n"])
def test_empty_yaml_documents_preserve_legacy_default(tmp_path: Path, text: str) -> None:
    path = tmp_path / "settings.yml"
    path.write_text(text)
    assert _load_profile_from_config(path) == "default"


@pytest.mark.parametrize("text", ["null\n", "profile: unknown\n", "execute: arbitrary\n"])
def test_invalid_yaml_is_not_an_empty_default(tmp_path: Path, text: str) -> None:
    path = tmp_path / "settings.yml"
    path.write_text(text)
    with pytest.raises(ContractError):
        _load_profile_from_config(path)


def test_no_config_does_not_discover_outside_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No --config remains no discovery, including an unrelated CWD config."""
    import cppulse.predictor.main as predictor
    import sys

    cwd = tmp_path / "unrelated"
    cwd.mkdir()
    (cwd / ".cppulserc.yml").write_text("profile: safety-critical\n")
    seen = []
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "argv", ["predictor", "--input", str(tmp_path / "data")])
    monkeypatch.setattr(predictor, "run", lambda **kw: seen.append(kw))
    predictor.main()
    assert seen[0]["profile"] == "default"


def test_absolute_explicit_config_outside_cwd_and_profile_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import cppulse.predictor.main as predictor
    import sys

    config = tmp_path / "selected.yml"
    config.write_text("profile: safety-critical # retained explicit selection\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    output = tmp_path / "result"
    output.mkdir()
    seen = []
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(predictor, "run", lambda **kw: seen.append(kw))
    argv = ["predictor", "--input", str(tmp_path / "data"), "--output", str(output), "--config", str(config)]
    monkeypatch.setattr(sys, "argv", argv)
    predictor.main()
    assert seen[-1]["profile"] == "safety-critical"
    monkeypatch.setattr(sys, "argv", [*argv, "--profile", "default"])
    predictor.main()
    assert seen[-1]["profile"] == "default"
    config.write_text("profile: unknown\n")
    with pytest.raises(ContractError):
        predictor.main()
    assert len(seen) == 2, "Explicit profile overrides value, but no longer bypasses config validation"


def test_predictor_profile_and_retained_settings_share_one_config_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import cppulse.predictor.main as predictor
    import sys
    path=tmp_path/'selected.json';path.write_text('{"profile":"safety-critical"}')
    out=tmp_path/'out';out.mkdir();read=Path.read_bytes;calls=[];seen=[]
    def changing(selected):
        raw=read(selected)
        if selected==path:
            calls.append(selected);path.write_text('{"profile":"default"}')
        return raw
    monkeypatch.setattr(Path,'read_bytes',changing)
    monkeypatch.setattr(predictor,'run',lambda **kwargs:seen.append(kwargs))
    monkeypatch.setattr(sys,'argv',['predictor','--input',str(tmp_path),'--output',str(out),'--config',str(path)])
    predictor.main()
    assert len(calls)==1 and seen[0]['profile']=='safety-critical'
    assert json.loads((out/'effective_config.json').read_bytes())['settings']['profile']=='safety-critical'
