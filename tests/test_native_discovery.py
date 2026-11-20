"""Native discovery uses declared installed inputs, never checkout heuristics."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any

import pytest

from cppulse import __version__
from cppulse.errors import CppulseError, UnsupportedVersion
from cppulse.native import NativeInstallation, discover_native


@pytest.fixture(autouse=True)
def isolated_discovery(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Do not let the host installation or explicit user settings select a tool."""
    for name in [
        "CPPULSE_ANALYZER",
        "CPPULSE_NATIVE_PREFIX",
        "CPPULSE_CLANG_RESOURCE_DIR",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "empty-python-prefix"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))


def executable(path: Path) -> Path:
    """Create an executable fixture that discovery must never run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"#!/bin/sh\nexit 73\n")
    path.chmod(0o755)
    return path


def resources(path: Path) -> Path:
    """Create the minimum builtin-header layout required by the analyzer."""
    (path / "include").mkdir(parents=True, exist_ok=True)
    (path / "include/stddef.h").write_text("/* synthetic builtin header */\n")
    return path


def install(prefix: Path) -> tuple[Path, dict[str, Any]]:
    """Create a relocatable native-install v1 fixture for this host."""
    analyzer = executable(prefix / "libexec/cppulse/cppulse-analyzer")
    resources(prefix / "share/cppulse/clang/19")
    (prefix / "lib/cppulse").mkdir(parents=True)
    document = {
        "version": "1.0.0",
        "tool_version": __version__,
        "target": {"platform": sys.platform, "machine": platform.machine()},
        "analyzer": "libexec/cppulse/cppulse-analyzer",
        "analyzer_sha256": hashlib.sha256(analyzer.read_bytes()).hexdigest(),
        "resource_dir": "share/cppulse/clang/19",
        "library_dirs": ["lib/cppulse"],
        "host_requirements": [
            {"name": "libclang", "constraint": "19", "purpose": "native parsing"}
        ],
        "limitations": ["Synthetic installation; no loader qualification."],
    }
    metadata = prefix / "share/cppulse/native-install.json"
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps(document))
    return metadata, document


def test_explicit_analyzer_has_precedence_without_executing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analyzer = executable(tmp_path / "explicit analyzer")
    monkeypatch.setenv("CPPULSE_ANALYZER", str(analyzer))
    monkeypatch.setenv("CPPULSE_NATIVE_PREFIX", str(tmp_path / "invalid-prefix"))
    selected = discover_native()
    assert selected.analyzer == analyzer
    assert selected.metadata is None
    assert selected.resource_dir is None
    assert selected.library_dirs == ()
    assert any("metadata" in value.lower() for value in selected.limitations)


@pytest.mark.parametrize("setting", ["CPPULSE_ANALYZER", "CPPULSE_NATIVE_PREFIX"])
@pytest.mark.parametrize("value", ["", "missing"])
def test_invalid_explicit_setting_never_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str, value: str
) -> None:
    path_bin = tmp_path / "bin"
    executable(path_bin / "cppulse-analyzer")
    monkeypatch.setenv("PATH", str(path_bin))
    monkeypatch.setenv(setting, "" if not value else str(tmp_path / value))
    with pytest.raises(CppulseError):
        discover_native()


def test_prefix_is_relocatable_and_precedes_python_prefix_and_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = tmp_path / "original"
    install(original)
    prefix = tmp_path / "relocated prefix with spaces"
    original.rename(prefix)
    fallback = tmp_path / "python"
    install(fallback)
    monkeypatch.setattr(sys, "prefix", str(fallback))
    monkeypatch.setenv("CPPULSE_NATIVE_PREFIX", str(prefix))
    selected = discover_native()
    assert selected.analyzer == prefix / "libexec/cppulse/cppulse-analyzer"
    assert selected.resource_dir == prefix / "share/cppulse/clang/19"
    assert selected.library_dirs == (prefix / "lib/cppulse",)
    assert selected.metadata == prefix / "share/cppulse/native-install.json"
    assert "Synthetic installation; no loader qualification." in selected.limitations


def test_python_prefix_manifest_precedes_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = tmp_path / "python"
    install(prefix)
    monkeypatch.setattr(sys, "prefix", str(prefix))
    path_bin = tmp_path / "bin"
    executable(path_bin / "cppulse-analyzer")
    monkeypatch.setenv("PATH", str(path_bin))
    assert discover_native().metadata == prefix / "share/cppulse/native-install.json"


def test_path_fallback_is_explicitly_unqualified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path_bin = tmp_path / "bin"
    analyzer = executable(path_bin / "cppulse-analyzer")
    monkeypatch.setenv("PATH", str(path_bin))
    selected = discover_native()
    assert selected.analyzer == analyzer
    assert selected.metadata is None
    assert selected.resource_dir is None
    assert selected.limitations


def test_missing_analyzer_is_actionable() -> None:
    with pytest.raises(CppulseError, match="CPPULSE_ANALYZER"):
        discover_native()


@pytest.mark.parametrize("selection", ["standalone", "prefix"])
def test_explicit_resource_override_is_validated_and_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selection: str
) -> None:
    if selection == "standalone":
        monkeypatch.setenv("CPPULSE_ANALYZER", str(executable(tmp_path / "analyzer")))
    else:
        prefix = tmp_path / "prefix"
        install(prefix)
        monkeypatch.setenv("CPPULSE_NATIVE_PREFIX", str(prefix))
    resource_dir = resources(tmp_path / "external resources")
    monkeypatch.setenv("CPPULSE_CLANG_RESOURCE_DIR", str(resource_dir))
    assert discover_native().resource_dir == resource_dir
    (resource_dir / "include/stddef.h").unlink()
    with pytest.raises(CppulseError, match="stddef.h"):
        discover_native()


def test_empty_resource_override_is_not_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CPPULSE_ANALYZER", str(executable(tmp_path / "analyzer")))
    monkeypatch.setenv("CPPULSE_CLANG_RESOURCE_DIR", "")
    with pytest.raises(CppulseError):
        discover_native()


@pytest.mark.parametrize("mutation", ["format", "tool", "platform", "machine"])
def test_metadata_rejects_unsupported_versions_or_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    prefix = tmp_path / "prefix"
    metadata, document = install(prefix)
    if mutation == "format":
        document["version"] = "99.0.0"
    elif mutation == "tool":
        document["tool_version"] = "99.0.0"
    elif mutation == "platform":
        document["target"]["platform"] = (
            "darwin" if sys.platform != "darwin" else "linux"
        )
    else:
        document["target"]["machine"] = "different-architecture"
    metadata.write_text(json.dumps(document))
    monkeypatch.setenv("CPPULSE_NATIVE_PREFIX", str(prefix))
    expected = UnsupportedVersion if mutation in {"format", "tool"} else CppulseError
    with pytest.raises(expected):
        discover_native()


@pytest.mark.parametrize("host,target", [("AMD64", "x86_64"), ("arm64", "aarch64")])
def test_only_equivalent_machine_aliases_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str, target: str
) -> None:
    prefix = tmp_path / "prefix"
    metadata, document = install(prefix)
    document["target"]["machine"] = target
    metadata.write_text(json.dumps(document))
    monkeypatch.setattr(platform, "machine", lambda: host)
    monkeypatch.setenv("CPPULSE_NATIVE_PREFIX", str(prefix))
    assert discover_native().metadata == metadata


@pytest.mark.parametrize(
    "relative",
    [
        "libexec/cppulse/cppulse-analyzer",
        "libexec/cppulse",
        "share/cppulse/clang/19",
        "share/cppulse/clang/19/include/stddef.h",
        "lib/cppulse",
        "share/cppulse/native-install.json",
    ],
)
def test_metadata_paths_never_follow_symlink_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    prefix = tmp_path / "prefix"
    install(prefix)
    selected = prefix / relative
    real = selected.with_name(selected.name + "-real")
    selected.rename(real)
    selected.symlink_to(real, target_is_directory=real.is_dir())
    monkeypatch.setenv("CPPULSE_NATIVE_PREFIX", str(prefix))
    with pytest.raises(CppulseError, match="[Ss]ymlink"):
        discover_native()


@pytest.mark.parametrize("mutation", ["checksum", "executable", "resource", "library"])
def test_declared_native_inputs_must_exist_and_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    prefix = tmp_path / "prefix"
    metadata, document = install(prefix)
    analyzer = prefix / document["analyzer"]
    if mutation == "checksum":
        analyzer.write_bytes(b"modified native executable")
    elif mutation == "executable":
        analyzer.chmod(0o644)
    elif mutation == "resource":
        (prefix / document["resource_dir"] / "include/stddef.h").unlink()
    else:
        (prefix / document["library_dirs"][0]).rmdir()
    monkeypatch.setenv("CPPULSE_NATIVE_PREFIX", str(prefix))
    with pytest.raises(CppulseError):
        discover_native()


def test_missing_optional_checksum_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = tmp_path / "prefix"
    metadata, document = install(prefix)
    document.pop("analyzer_sha256")
    metadata.write_text(json.dumps(document))
    monkeypatch.setenv("CPPULSE_NATIVE_PREFIX", str(prefix))
    assert any("checksum" in value.lower() for value in discover_native().limitations)


def test_invalid_python_manifest_does_not_silently_use_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = tmp_path / "python"
    metadata, _ = install(prefix)
    metadata.write_text("not json")
    monkeypatch.setattr(sys, "prefix", str(prefix))
    path_bin = tmp_path / "bin"
    executable(path_bin / "cppulse-analyzer")
    monkeypatch.setenv("PATH", str(path_bin))
    with pytest.raises(CppulseError):
        discover_native()


def test_child_environment_uses_only_selected_library_and_resource_paths(
    tmp_path: Path,
) -> None:
    library = tmp_path / "selected lib"
    resource = tmp_path / "selected resource"
    selected = NativeInstallation(tmp_path / "analyzer", resource, (library,), None)
    original = {
        "KEEP": "value",
        "LD_LIBRARY_PATH": "/old/source/build/lib",
        "DYLD_LIBRARY_PATH": "/old/mac/build/lib",
        "CPPULSE_CLANG_RESOURCE_DIR": "/old/clang",
    }
    environment = selected.environment(original)
    variable = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    assert environment[variable] == str(library)
    assert environment["CPPULSE_CLANG_RESOURCE_DIR"] == str(resource)
    assert environment["KEEP"] == "value"
    assert "/old/" not in " ".join(environment.values())
    assert original["CPPULSE_CLANG_RESOURCE_DIR"] == "/old/clang"


def test_standalone_environment_removes_unselected_loader_and_resource_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = NativeInstallation(tmp_path / "analyzer", None, (), None)
    for variable in [
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "CPPULSE_CLANG_RESOURCE_DIR",
    ]:
        monkeypatch.setenv(variable, "/old/build")
    environment = selected.environment()
    assert (
        not {
            "LD_LIBRARY_PATH",
            "DYLD_LIBRARY_PATH",
            "CPPULSE_CLANG_RESOURCE_DIR",
        }
        & environment.keys()
    )
    assert os.environ["CPPULSE_CLANG_RESOURCE_DIR"] == "/old/build"
