"""Actual installed-native qualification and package-integrity regressions."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile

import pytest

from cppulse.contracts import validate

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cppulse_native_packager", ROOT / "scripts/package_native.py"
)
assert SPEC is not None and SPEC.loader is not None
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)

pytestmark = pytest.mark.skipif(
    platform.system() != "Linux" or platform.machine() != "x86_64",
    reason="Native artifact qualification is currently Linux x86_64 only",
)


@pytest.fixture(scope="module")
def native_configuration(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Configure a real release build with mandatory test dependencies disabled."""
    build = tmp_path_factory.mktemp("native-build-without-tests")
    result = subprocess.run(
        [
            "cmake",
            "-S",
            str(ROOT / "analyzer-core"),
            "-B",
            str(build),
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_TESTING=OFF",
            "-DCMAKE_DISABLE_FIND_PACKAGE_GTest=TRUE",
            "-DCMAKE_INSTALL_LIBDIR=lib",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BUILD_TESTING:BOOL=OFF" in (build / "CMakeCache.txt").read_text()
    assert not (build / "cppulse-analyzer-tests").exists()
    return build


@pytest.fixture(scope="module")
def native_candidate(
    native_configuration: Path, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, str]:
    """Build, install and qualify actual native bytes rather than mock executables."""
    resource = os.environ.get("CPPULSE_CLANG_RESOURCE_DIR")
    assert (
        resource
    ), "CPPULSE_CLANG_RESOURCE_DIR must select the matching installed Clang resources"
    return PACKAGER.build_package(
        native_configuration,
        tmp_path_factory.mktemp("native-candidate"),
        Path(resource),
    )


def test_build_testing_off_needs_no_gtest(
    native_configuration: Path, native_candidate: dict[str, str]
) -> None:
    cache = (native_configuration / "CMakeCache.txt").read_text()
    assert "GTest_DIR:" not in cache
    assert not (native_configuration / "cppulse-analyzer-tests").exists()
    assert Path(native_candidate["archive"]).is_file()


def test_manifest_is_relative_and_binary_digest_matches(
    native_candidate: dict[str, str]
) -> None:
    prefix = Path(native_candidate["prefix"])
    metadata = json.loads(Path(native_candidate["manifest"]).read_text())
    validate("native_install", metadata)
    assert metadata["analyzer"] == "libexec/cppulse/cppulse-analyzer"
    assert metadata["resource_dir"].startswith("share/cppulse/clang/")
    assert metadata["library_dirs"] == ["lib/cppulse"]
    binary = prefix / metadata["analyzer"]
    assert (
        hashlib.sha256(binary.read_bytes()).hexdigest() == metadata["analyzer_sha256"]
    )
    assert str(ROOT) not in json.dumps(metadata)
    names = {entry["name"] for entry in metadata["host_requirements"]}
    assert any(name.startswith("libclang-") for name in names)
    assert any(name.startswith("libLLVM") for name in names)
    assert "C++ compiler and standard-library headers" in names
    assert (prefix / metadata["resource_dir"] / "include/stddef.h").is_file()


def test_relocated_binary_runs_without_checkout_or_loader_overrides(
    native_candidate: dict[str, str], tmp_path: Path
) -> None:
    prefix = tmp_path / "another installation with spaces"
    shutil.copytree(Path(native_candidate["prefix"]), prefix)
    metadata = json.loads((prefix / "share/cppulse/native-install.json").read_text())
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "LD_LIBRARY_PATH",
            "LD_PRELOAD",
            "CPPULSE_CLANG_RESOURCE_DIR",
            "LIBCLANG_ROOT",
            "CMAKE_PREFIX_PATH",
        }
    }
    environment["PATH"] = "/usr/bin:/bin"
    working = tmp_path / "unrelated"
    working.mkdir()
    binary = prefix / metadata["analyzer"]
    result = subprocess.run(
        [str(binary), "--help"],
        cwd=working,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--resource-dir" in result.stdout
    dynamic = subprocess.run(
        ["readelf", "-d", str(binary)], capture_output=True, text=True, check=True
    ).stdout
    assert "$ORIGIN/../../lib/cppulse" in dynamic
    assert str(ROOT.parent / "toolchain") not in dynamic
    proof = json.loads((prefix / "share/cppulse/native-verification.json").read_text())
    assert proof["relocation"] == "passed"
    assert proof["standard_headers"] == ["string", "vector"]
    assert proof["parse_errors"] == 0


def test_archive_retains_notices_and_hash_inventory(
    native_candidate: dict[str, str]
) -> None:
    prefix = Path(native_candidate["prefix"])
    archive = Path(native_candidate["archive"])
    assert (
        hashlib.sha256(archive.read_bytes()).hexdigest() == native_candidate["sha256"]
    )
    assert (
        Path(native_candidate["checksum_file"])
        .read_text()
        .startswith(native_candidate["sha256"])
    )
    for name in [
        "cppulse-LICENSE.txt",
        "fmt-copyright.txt",
        "spdlog-copyright.txt",
        "clang-builtins-copyright.txt",
    ]:
        assert (prefix / "share/licenses/cppulse-native" / name).stat().st_size > 100
    inventory = json.loads((prefix / "share/cppulse/native-files.json").read_text())
    indexed = set()
    for entry in inventory["files"]:
        path = prefix / entry["path"]
        assert path.is_file()
        assert path.stat().st_size == entry["size_bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        indexed.add(entry["path"])
    assert "share/cppulse/native-install.json" in indexed
    assert "share/cppulse/native-files.json" not in indexed
    with tarfile.open(archive) as stream:
        for member in stream.getmembers():
            assert not Path(member.name).is_absolute()
            assert ".." not in Path(member.name).parts
            assert not member.issym() and not member.islnk()


def test_existing_native_candidate_is_never_replaced(
    native_candidate: dict[str, str], native_configuration: Path
) -> None:
    archive = Path(native_candidate["archive"])
    before = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError, match="already exists"):
        PACKAGER.build_package(
            native_configuration,
            archive.parent,
            Path(os.environ["CPPULSE_CLANG_RESOURCE_DIR"]),
        )
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == before


def test_missing_resource_is_rejected_before_candidate_writes(tmp_path: Path) -> None:
    output = tmp_path / "candidate"
    with pytest.raises(PACKAGER.NativePackageError, match="include/stddef.h"):
        PACKAGER.build_package(
            tmp_path / "unconfigured", output, tmp_path / "missing-resources"
        )
    assert not output.exists()
