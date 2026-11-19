"""Per-rule capabilities must constrain public project configuration.

These are real JSON project inputs against the public settings API and the
packaged authoritative per-rule schemas. No detector or native job executes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from cppulse.config import effective_config, read_settings
from cppulse.errors import ContractError
from cppulse.tooling import load_rule_registry


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """An isolated project, without Git, user settings or executable code."""
    root = tmp_path / "project"
    root.mkdir()
    return root


def settings_file(project: Path, document: dict[str, Any]) -> Path:
    """Retain the exact JSON passed to the settings reader."""
    path = project / ".cppulserc.json"
    path.write_text(json.dumps(document, allow_nan=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("rule_id", ["CPP-MEM-001", "CPP-MOD-001", "MISRA-001"])
@pytest.mark.parametrize("option", ["warning_threshold", "error_threshold"])
def test_rule_without_threshold_capability_refuses_threshold(
    project: Path, rule_id: str, option: str
) -> None:
    """A generic known option must not bypass its selected rule's capability."""
    schema = next(row["configuration_schema"] for row in load_rule_registry()["rules"]
                  if row["id"] == rule_id)
    supplied = {option: 9}
    # The published per-rule contract already rejects this setting. The bug is
    # that the public project reader admitted it for later silent omission.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(supplied, schema)
    path = settings_file(project, {"rules": {rule_id: supplied}})
    with pytest.raises(ContractError, match=option):
        read_settings(path)


@pytest.mark.parametrize("rule_id", ["CPP-CX-001", "CPP-CX-002", "CPP-CX-003"])
def test_supported_threshold_boundaries_and_enabled_value_are_preserved(
    project: Path, rule_id: str
) -> None:
    supplied = {"enabled": False, "warning_threshold": 0, "error_threshold": 2147483647}
    path = settings_file(project, {"rules": {rule_id: supplied}})
    assert read_settings(path)["rules"][rule_id] == supplied
    selected = effective_config(project, project.parent / "output")
    assert selected.settings["rules"][rule_id] == supplied
    assert selected.settings["rules"][rule_id]["enabled"] is False


@pytest.mark.parametrize("option", ["warning_threshold", "error_threshold"])
@pytest.mark.parametrize("value", [True, False, "9", 9.5, -1, 2147483648, None])
def test_supported_threshold_rejects_coercion_noninteger_and_out_of_range(
    project: Path, option: str, value: Any
) -> None:
    path = settings_file(project, {"rules": {"CPP-CX-001": {option: value}}})
    with pytest.raises(ContractError):
        read_settings(path)


@pytest.mark.parametrize("value", [0, 1, "false", None])
def test_enabled_requires_boolean_without_coercion(project: Path, value: Any) -> None:
    path = settings_file(project, {"rules": {"CPP-MEM-001": {"enabled": value}}})
    with pytest.raises(ContractError):
        read_settings(path)


@pytest.mark.parametrize("suffix", [".json", ".yml"])
@pytest.mark.parametrize("option", ["warning_threshold", "error_threshold",
                                    "max_file_bytes", "max_token_records"])
def test_native_integer_options_reject_integral_float_spelling(
    project: Path, suffix: str, option: str
) -> None:
    """The Python producer must not admit a token rejected by native loading."""
    import yaml

    document = ({"rules": {"CPP-CX-001": {option: 9.0}}}
                if option.endswith("threshold") else {option: 9.0})
    path = project / (".cppulserc" + suffix)
    path.write_text(json.dumps(document) if suffix == ".json"
                    else yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ContractError):
        read_settings(path)


@pytest.mark.parametrize("document", [
    {"unrecognized": True},
    {"rules": {"CPP-CX-999": {"enabled": False}}},
    {"rules": {"CPP-CX-001": {"unrecognized": 9}}},
    {"rules": {"CPP-MEM-001": {"unrecognized": 9}}},
    {"rules": {"CPP-MEM-001": None}},
])
def test_unknown_root_rule_and_rule_option_are_not_ignored(
    project: Path, document: dict[str, Any]
) -> None:
    with pytest.raises(ContractError):
        read_settings(settings_file(project, document))


def test_missing_rule_settings_keep_defaults_and_profile_provenance(project: Path) -> None:
    before = load_rule_registry()
    defaults = effective_config(project, project.parent / "default-output")
    assert defaults.profile_source == "default"
    assert defaults.settings["profile"] == "default" and defaults.settings["rules"] == {}
    path = settings_file(project, {"profile": "safety-critical",
                                   "rules": {"CPP-MEM-001": {"enabled": False}}})
    assert read_settings(path)["rules"]["CPP-MEM-001"] == {"enabled": False}
    selected = effective_config(project, project.parent / "project-output")
    assert selected.profile_source == "config" and selected.settings["profile"] == "safety-critical"
    override = effective_config(project, project.parent / "explicit-output", profile="default")
    assert override.profile_source == "command" and override.settings["profile"] == "default"
    assert override.settings["rules"]["CPP-MEM-001"]["enabled"] is False
    assert load_rule_registry() == before, "Project validation must not mutate registry defaults"
