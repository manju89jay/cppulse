"""Installation metadata is portable data, not an executable setup recipe."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from cppulse.contracts import load_schema, validate
from cppulse.errors import ContractError, UnsupportedVersion


def native_install_document() -> dict[str, Any]:
    """Return a synthetic qualified-target example with prefix-relative paths."""
    return {
        "version": "1.0.0",
        "tool_version": "0.2.0.dev0",
        "target": {
            "platform": "linux",
            "machine": "x86_64",
            "libc": "glibc",
            "libc_version": "2.41",
        },
        "analyzer": "libexec/cppulse/cppulse-analyzer",
        "analyzer_sha256": "a" * 64,
        "resource_dir": "share/cppulse/clang/19",
        "library_dirs": ["lib/cppulse"],
        "host_requirements": [
            {"name": "glibc", "constraint": ">=2.41", "purpose": "native runtime"}
        ],
        "limitations": ["Only the declared target has been qualified."],
    }


def test_native_install_defaults_to_its_own_v1_contract() -> None:
    assert load_schema("native_install")["properties"]["version"] == {"const": "1.0.0"}
    validate("native_install", native_install_document())


def test_optional_binary_hash_and_runtime_details_are_not_fabricated() -> None:
    document = native_install_document()
    document.pop("analyzer_sha256")
    document["target"].pop("libc")
    document["target"].pop("libc_version")
    document["library_dirs"] = []
    document["host_requirements"] = []
    validate("native_install", document)


@pytest.mark.parametrize(
    "field,path",
    [
        ("analyzer", "/workspace/session/build/cppulse-analyzer"),
        ("analyzer", "C:\\build\\cppulse-analyzer.exe"),
        ("analyzer", "../cppulse-analyzer"),
        ("analyzer", "."),
        ("resource_dir", "/usr/lib/clang/19"),
        ("resource_dir", "share/../../outside"),
        ("resource_dir", "share//clang"),
        ("library_dirs", "../lib"),
        ("library_dirs", "/workspace/toolchain/lib"),
        ("library_dirs", "lib\\cppulse"),
    ],
)
def test_install_paths_cannot_escape_or_encode_session_locations(
    field: str, path: str
) -> None:
    document = native_install_document()
    document[field] = [path] if field == "library_dirs" else path
    with pytest.raises(ContractError) as caught:
        validate("native_install", document)
    assert caught.value.code == "UNSAFE_PATH"


def test_directory_dot_is_allowed_but_file_directory_alias_is_not() -> None:
    document = native_install_document()
    document["resource_dir"] = "."
    document["library_dirs"] = ["."]
    validate("native_install", document)
    document["resource_dir"] = document["analyzer"]
    with pytest.raises(ContractError) as caught:
        validate("native_install", document)
    assert caught.value.code == "INSTALL_PATH_COLLISION"


def test_native_install_unknown_major_is_not_risk_v1_migration() -> None:
    document = native_install_document()
    document["version"] = "2.0.0"
    with pytest.raises(UnsupportedVersion):
        validate("native_install", document)


@pytest.mark.parametrize(
    "field,value",
    [("install_command", "curl | shell"), ("analyzer_sha256", "not-a-digest")],
)
def test_install_metadata_rejects_hidden_commands_or_invalid_integrity(
    field: str, value: str
) -> None:
    document = native_install_document()
    document[field] = value
    with pytest.raises(ContractError):
        validate("native_install", document)


def test_native_install_duplicate_requirements_are_ambiguous() -> None:
    document = native_install_document()
    document["host_requirements"].append(deepcopy(document["host_requirements"][0]))
    with pytest.raises(ContractError, match="Duplicate"):
        validate("native_install", document)
