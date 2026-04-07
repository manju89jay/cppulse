"""Tests for predictor config file loading (_load_profile_from_config)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.main import _load_profile_from_config


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

    def test_unknown_profile_returns_default(self, tmp_config):
        p = tmp_config(".cppulserc.yml", "profile: unknown-profile\n")
        assert _load_profile_from_config(p) == "default"

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

    def test_nonexistent_file_returns_default(self, tmp_path: Path):
        p = tmp_path / "nonexistent.yml"
        assert _load_profile_from_config(p) == "default"

    def test_empty_file_returns_default(self, tmp_config):
        p = tmp_config(".cppulserc.yml", "")
        assert _load_profile_from_config(p) == "default"

    def test_quoted_profile_value(self, tmp_config):
        p = tmp_config(".cppulserc.yml", "profile: 'safety-critical'\n")
        assert _load_profile_from_config(p) == "safety-critical"
