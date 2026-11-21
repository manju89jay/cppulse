"""Ruleset contracts: real local data, precedence, identities and negative controls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cppulse.config import effective_config
from cppulse.errors import ContractError
from cppulse.rulesets import resolve_ruleset, clang_tidy_arguments
from cppulse.tooling import load_rule_registry


def pack(path: Path, **values: object) -> Path:
    """Write an actual independently editable pack document."""
    path.write_text(
        json.dumps(
            {"format_version": "1.0.0", "name": path.stem, "version": "1.0.0", **values}
        )
    )
    return path


def provider() -> dict:
    """Explicit finite producer options; no reliance on clang-tidy defaults."""
    return {
        "version": "19.1.7",
        "scope_files": ["main.cpp"],
        "checks": {
            "bugprone-use-after-move": {"enabled": True},
            "bugprone-dangling-handle": {
                "enabled": True,
                "options": {
                    "HandleClasses": [
                        "std::basic_string_view",
                        "std::experimental::basic_string_view",
                    ]
                },
            },
            "bugprone-unused-return-value": {
                "enabled": True,
                "options": {
                    "CheckedFunctions": ["::qual::status"],
                    "CheckedReturnTypes": ["::qual::Error"],
                    "AllowCastToVoid": False,
                },
            },
        },
    }


def test_preset_inherited_project_command_and_inspectable_identity(
    tmp_path: Path,
) -> None:
    base = pack(
        tmp_path / "base.json",
        preset="no-native",
        native={
            "rules": {"CPP-CX-001": {"enabled": True, "warning_threshold": 30}},
            "exclude_paths": ["vendor/**"],
        },
    )
    child = pack(
        tmp_path / "child.json",
        inherits=[base.name],
        native={"rules": {"CPP-CX-001": {"warning_threshold": 20}}},
        providers={"clang-tidy": provider()},
    )
    project = tmp_path / ".cppulserc.json"
    project.write_text(
        json.dumps(
            {
                "ruleset": child.name,
                "profile": "safety-critical",
                "rules": {"CPP-CX-001": {"warning_threshold": 10}},
            }
        )
    )
    selected = effective_config(
        tmp_path,
        tmp_path / "out",
        profile="default",
        rule_options={"CPP-CX-001": {"warning_threshold": 5}},
    )
    assert (
        selected.settings["profile"] == "default"
        and selected.profile_source == "command"
    )
    assert selected.settings["rules"]["CPP-CX-001"] == {
        "enabled": True,
        "warning_threshold": 5,
    }
    assert selected.settings["rules"]["CPP-MEM-001"]["enabled"] is False
    assert selected.settings["exclude_paths"] == ["vendor/**"]
    identity = selected.as_dict()["ruleset"]
    assert identity["origins"]["native.rules.CPP-CX-001.warning_threshold"] == "command"
    assert identity["origins"]["native.rules.CPP-MEM-001.enabled"].endswith(
        "base.json#preset=no-native"
    )
    assert (
        identity["packs"][0]["sha256"] == hashlib.sha256(base.read_bytes()).hexdigest()
    )
    assert identity["registry_format_version"] == "2.0.0"
    assert identity["tool_version"] == "0.2.0.dev2"
    assert identity["native_defaults"]["CPP-CX-001"]["error_threshold"] == 25
    assert (
        identity["origins"]["native.rules.CPP-CX-001.error_threshold"]
        == "registry-default"
    )
    assert identity["origins"]["native.max_file_bytes"] == "default"
    assert len(identity["native_rule_versions"]) == 22
    assert set(identity["native_rule_versions"].values()) != {"2.0.0"}
    assert "ruleset" not in selected.settings and "providers" not in selected.settings


def test_command_pack_selection_and_repeatable_identity_change_on_parent_content(
    tmp_path: Path,
) -> None:
    parent = pack(
        tmp_path / "parent.json", native={"rules": {"CPP-MEM-001": {"enabled": False}}}
    )
    child = pack(tmp_path / "child.json", inherits=[parent.name])
    (tmp_path / ".cppulserc.json").write_text('{"ruleset":"nonexistent.json"}')
    first = effective_config(tmp_path, tmp_path / "out", ruleset=child)
    assert (
        first.ruleset
        == effective_config(tmp_path, tmp_path / "out", ruleset=child).ruleset
    )
    before = first.ruleset["digest"]
    parent.write_text(parent.read_text() + "\n")
    changed = effective_config(tmp_path, tmp_path / "out", ruleset=child)
    assert changed.ruleset["digest"] != before
    assert (
        changed.settings == first.settings
    ), "Content identity changes even with identical detector semantics"
    assert changed.ruleset["selection_origin"] == "command"


def test_project_settings_and_hash_bind_one_read_even_when_live_file_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = pack(tmp_path / "review.json")
    project = tmp_path / ".cppulserc.json"
    original = json.dumps(
        {"ruleset": selected.name, "profile": "safety-critical"}
    ).encode()
    project.write_bytes(original)
    read = Path.read_bytes
    calls = []

    def changing(path):
        body = read(path)
        if path == project:
            calls.append(path)
            project.write_text(
                json.dumps({"ruleset": selected.name, "profile": "default"})
            )
        return body

    monkeypatch.setattr(Path, "read_bytes", changing)
    config = effective_config(tmp_path, tmp_path / "out")
    assert len(calls) == 1 and config.settings["profile"] == "safety-critical"
    assert (
        config.ruleset["project_config_sha256"] == hashlib.sha256(original).hexdigest()
    )
    assert (
        config.ruleset["project_config_sha256"]
        != hashlib.sha256(read(project)).hexdigest()
    )


@pytest.mark.parametrize(
    "invalid",
    [
        {"format_version": "2.0.0"},
        {"version": 1},
        {"version": "1.2"},
        {"preset": "safety-critical"},
        {"weights": {"memory": -1}},
        {"command": ["touch", "sentinel"]},
        {"plugin": "evil.module"},
        {"native": {"select": ["CPP-POL-001"]}},
        {"native": {"rules": {"CPP-MEM-001": {"warning_threshold": 9}}}},
        {"native": {"rules": {"CPP-CX-001": {"warning_threshold": 9.0}}}},
        {"native": {"rules": {"CPP-MEM-001": {"enabled": 1}}}},
        {"native": {"rules": {"CPP-MEM-001": {"weight": 100}}}},
        {"native": {"include_paths": ["src/**"]}},
        {"providers": {"unknown": {}}},
    ],
)
def test_unknown_options_types_versions_weights_and_code_rejected(
    tmp_path: Path, invalid: dict
) -> None:
    with pytest.raises(ContractError):
        resolve_ruleset(pack(tmp_path / "bad.json", **invalid))
    assert not (tmp_path / "sentinel").exists()


@pytest.mark.parametrize(
    "mutation", ["version", "check", "option", "scope", "bool", "unpin"]
)
def test_provider_contract_is_finite_and_explicit(
    tmp_path: Path, mutation: str
) -> None:
    value = provider()
    if mutation == "version":
        value["version"] = "20.0.0"
    elif mutation == "check":
        value["checks"]["arbitrary-new-check"] = {"enabled": True}
    elif mutation == "scope":
        value["scope_files"] = ["../outside.cpp"]
    elif mutation == "bool":
        value["checks"]["bugprone-unused-return-value"]["options"][
            "AllowCastToVoid"
        ] = "false"
    elif mutation == "unpin":
        del value["checks"]["bugprone-unused-return-value"]["options"][
            "CheckedFunctions"
        ]
    else:
        value["checks"]["bugprone-use-after-move"]["options"] = {"unknown": True}
    with pytest.raises(ContractError):
        resolve_ruleset(pack(tmp_path / "bad.json", providers={"clang-tidy": value}))


def test_cycles_duplicate_keys_bounds_and_conflicting_named_content(
    tmp_path: Path,
) -> None:
    a = pack(tmp_path / "a.json", inherits=["b.json"])
    pack(tmp_path / "b.json", inherits=["a.json"])
    with pytest.raises(ContractError, match="cycle"):
        resolve_ruleset(a)
    a.write_text('{"format_version":"1.0.0","name":"x","name":"y","version":"1.0.0"}')
    with pytest.raises(ContractError, match="Duplicate"):
        resolve_ruleset(a)
    a.write_text(" " * 65537)
    with pytest.raises(ContractError, match="64 KiB"):
        resolve_ruleset(a)
    pack(a, name="same", native={"select": []})
    pack(tmp_path / "b.json", name="same", native={"select": ["CPP-MEM-001"]})
    root = pack(tmp_path / "root.json", inherits=["a.json", "b.json"])
    with pytest.raises(ContractError, match="Conflicting content"):
        resolve_ruleset(root)


def test_pack_loading_never_executes_or_networks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket
    import subprocess

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail(
            "Resolving a data pack must not execute a command or contact a network"
        )

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    p = pack(
        tmp_path / "safe.json",
        preset="all-native",
        providers={"clang-tidy": provider()},
    )
    selected = resolve_ruleset(p)
    assert len(selected.native["rules"]) == 22
    args = clang_tidy_arguments(selected.providers["clang-tidy"])
    config = json.loads(args[1].removeprefix("--config="))
    assert (
        config["CheckOptions"]["bugprone-unused-return-value.AllowCastToVoid"]
        == "false"
    )
    assert (
        config["CheckOptions"]["bugprone-unused-return-value.CheckedFunctions"]
        == "::qual::status"
    )


def test_nonregular_pack_is_rejected_without_waiting_for_a_writer(
    tmp_path: Path,
) -> None:
    import os

    path = tmp_path / "pack.pipe"
    os.mkfifo(path)
    try:
        with pytest.raises(ContractError, match="ordinary data file"):
            resolve_ruleset(path)
    finally:
        path.unlink()  # Empty test-owned FIFO has no body to preserve.


def test_preset_baseline_does_not_override_inherited_explicit_options_or_origins(
    tmp_path: Path,
) -> None:
    parent = pack(
        tmp_path / "parent.json",
        native={
            "rules": {
                "CPP-CX-001": {"warning_threshold": 7, "error_threshold": 12},
                "CPP-MEM-001": {"enabled": False},
            }
        },
    )
    child = pack(tmp_path / "child.json", inherits=[parent.name], preset="all-native")
    result = resolve_ruleset(child)
    assert result.native["rules"]["CPP-MEM-001"]["enabled"] is False
    assert result.native["rules"]["CPP-MOD-001"]["enabled"] is True
    assert result.native["rules"]["CPP-CX-001"]["warning_threshold"] == 7
    assert result.identity["origins"][
        "native.rules.CPP-CX-001.warning_threshold"
    ] == str(parent)
    assert result.identity["origins"]["native.rules.CPP-CX-001.error_threshold"] == str(
        parent
    )


@pytest.mark.parametrize("suffix", ["json", "yaml"])
def test_legacy_settings_keep_existing22_selection_and_scoring_separate(
    tmp_path: Path, suffix: str
) -> None:
    import yaml

    doc = {"profile": "safety-critical", "rules": {"CPP-CX-001": {"enabled": False}}}
    (tmp_path / (".cppulserc." + suffix)).write_text(
        json.dumps(doc) if suffix == "json" else yaml.safe_dump(doc)
    )
    before = load_rule_registry()
    selected = effective_config(tmp_path, tmp_path / "out")
    assert selected.ruleset is None and "ruleset" not in selected.as_dict()
    assert selected.settings["profile"] == "safety-critical"
    assert selected.settings["rules"] == doc["rules"]
    assert len(load_rule_registry()["rules"]) == 22 and load_rule_registry() == before
