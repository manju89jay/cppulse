#!/usr/bin/env python3
"""Prepare a locally verified, relocatable Linux native analyzer candidate.

Run with the cppulse Python package importable (PYTHONPATH=python in a checkout).
The candidate bundles fmt/spdlog and matching selected Clang builtin headers;
libclang/LLVM, the system runtime and C++ standard-library headers remain host
requirements. This script builds/packages locally and never publishes anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import posixpath
import re
import shutil
import subprocess
import tarfile
import tempfile
from typing import Any, Mapping

from cppulse import __version__
from cppulse.contracts import validate


class NativePackageError(ValueError):
    """A native candidate cannot be built, relocated or honestly qualified."""


def _run(
    argv: list[str], *, cwd: Path | None = None, env: Mapping[str, str] | None = None
) -> str:
    """Run one explicit local command and retain useful failure diagnostics."""
    result = subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise NativePackageError(
            f"Command failed ({result.returncode}): {argv!r}\n{result.stdout}{result.stderr}"
        )
    return result.stdout + result.stderr


def _sha256(path: Path) -> str:
    """Hash bytes without loading large resources into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_environment() -> dict[str, str]:
    """Remove build-tree discovery and loader overrides for installed checks."""
    environment = dict(os.environ)
    for name in (
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "CPPULSE_CLANG_RESOURCE_DIR",
        "LIBCLANG_ROOT",
        "CMAKE_PREFIX_PATH",
    ):
        environment.pop(name, None)
    environment["PATH"] = "/usr/bin:/bin"
    return environment


def _dependencies(binary: Path, *, clean: bool = False) -> dict[str, Path]:
    """Inspect this locally built ELF dependency closure, including transitive libs."""
    output = _run(["ldd", str(binary)], env=_runtime_environment() if clean else None)
    if "not found" in output:
        raise NativePackageError(f"Unresolved native dependencies:\n{output}")
    dependencies = {}
    for line in output.splitlines():
        match = re.match(r"\s*(\S+)\s+=>\s+(.+?)\s+\(0x[0-9a-f]+\)", line)
        if match:
            name, path = match.groups()
            dependencies[name] = Path(path).resolve(strict=True)
        else:
            loader = re.match(r"\s*(/.+?)\s+\(0x[0-9a-f]+\)", line)
            if loader:
                path = Path(loader.group(1)).resolve(strict=True)
                dependencies[path.name] = path
    if not dependencies:
        raise NativePackageError(
            "No dynamic native runtime dependencies were identified"
        )
    return dependencies


def _install_directory(build_dir: Path, name: str) -> str:
    """Read the configured GNUInstallDirs path without inventing layout assumptions."""
    cache = (build_dir / "CMakeCache.txt").read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}:[^=]+=(.*)$", cache, re.MULTILINE)
    if match is None:
        raise NativePackageError(
            f"Missing {name}; reconfigure the analyzer with GNUInstallDirs support"
        )
    value = match.group(1)
    if (
        not value
        or Path(value).is_absolute()
        or ".." in Path(value).parts
        or "\\" in value
    ):
        raise NativePackageError(f"Packaging requires a relative {name}, got {value!r}")
    return Path(value).as_posix()


def _notice(explicit: Path | None, origins: list[Path], package_name: str) -> Path:
    """Find a supplied or Debian-installed notice for the exact distributed component."""
    if explicit is not None:
        if not explicit.is_file():
            raise NativePackageError(f"Missing supplied license notice: {explicit}")
        return explicit
    for origin in origins:
        for ancestor in (origin, *origin.parents):
            candidate = ancestor / "share" / "doc" / package_name / "copyright"
            if candidate.is_file():
                return candidate
    candidate = Path("/usr/share/doc") / package_name / "copyright"
    if candidate.is_file():
        return candidate
    raise NativePackageError(
        f"License notice for {package_name} is unavailable; supply its explicit notice option"
    )


def _verify_relocation(
    prefix: Path, metadata: dict[str, Any], bundled: set[str]
) -> dict[str, Any]:
    """Run the installed binary and standard-library parse after moving its prefix."""
    with tempfile.TemporaryDirectory(prefix="cppulse-native-relocation-") as temporary:
        root = Path(temporary)
        relocated = root / "relocated installation with spaces"
        shutil.copytree(prefix, relocated)
        binary = relocated / metadata["analyzer"]
        dynamic = _run(["readelf", "-d", str(binary)])
        rpaths = re.findall(r"\((?:RUNPATH|RPATH)\).*?\[(.*?)\]", dynamic)
        expected = "$ORIGIN/" + posixpath.relpath(
            metadata["library_dirs"][0], posixpath.dirname(metadata["analyzer"])
        )
        if rpaths != [expected]:
            raise NativePackageError(
                f"Unexpected installed RPATH {rpaths!r}; expected only {expected!r}"
            )
        dependencies = _dependencies(binary, clean=True)
        for name in bundled:
            expected_library = (
                relocated / metadata["library_dirs"][0] / name
            ).resolve()
            if dependencies.get(name) != expected_library:
                raise NativePackageError(
                    f"Bundled {name} was not resolved inside the relocated prefix"
                )
        project = root / "input project"
        working = root / "unrelated working directory"
        output = root / "analysis output"
        project.mkdir()
        working.mkdir()
        (project / "sample.cpp").write_text(
            "#include <string>\n#include <vector>\n"
            "std::string sample() { std::vector<std::string> names; return std::string{}; }\n",
            encoding="utf-8",
        )
        _run([str(binary), "--help"], cwd=working, env=_runtime_environment())
        _run(
            [
                str(binary),
                "--repo",
                str(project),
                "--output",
                str(output),
                "--resource-dir",
                str(relocated / metadata["resource_dir"]),
            ],
            cwd=working,
            env=_runtime_environment(),
        )
        findings = json.loads((output / "findings.json").read_text())
        validate("findings", findings, version="prototype_v1")
        files = findings["metadata"]["analysis"]["files"]
        if (
            len(files) != 1
            or files[0]["status"] != "analyzed"
            or files[0]["error_count"] != 0
        ):
            raise NativePackageError(
                f"Installed standard-library parse is incomplete: {files!r}"
            )
        return {
            "relocation": "passed",
            "prefix_with_spaces": True,
            "loader_overrides_removed": True,
            "standard_headers": ["string", "vector"],
            "parse_errors": 0,
            "rpath": expected,
        }


def build_package(
    build_dir: Path,
    output_dir: Path,
    resource_dir: Path,
    *,
    cmake: str = "cmake",
    jobs: int = 4,
    notices: Mapping[str, Path] | None = None,
) -> dict[str, str]:
    """Build and locally qualify one immutable-named Linux x86-64 native candidate.

    Existing candidate paths are never replaced. Host dependencies are declared,
    not bundled indiscriminately or claimed to work on untested platforms.
    """
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise NativePackageError(
            "Only the tested Linux x86_64 native packaging target is supported"
        )
    if jobs < 1:
        raise NativePackageError("Build jobs must be positive")
    resource_dir = resource_dir.resolve()
    if not (resource_dir / "include" / "stddef.h").is_file():
        raise NativePackageError("Resource directory must contain include/stddef.h")
    if not (build_dir / "CMakeCache.txt").is_file():
        raise NativePackageError(
            "Configure analyzer-core before preparing a native package"
        )
    build_dir = build_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = f"cppulse-native-{__version__}-linux-x86_64"
    final_prefix = output_dir / candidate
    final_archive = output_dir / (candidate + ".tar.gz")
    checksum_path = final_archive.with_name(final_archive.name + ".sha256")
    if final_prefix.exists() or final_archive.exists() or checksum_path.exists():
        raise FileExistsError(
            f"Candidate already exists; choose another output directory: {candidate}"
        )
    _run(
        [
            cmake,
            "--build",
            str(build_dir),
            "--target",
            "cppulse-analyzer",
            "-j",
            str(jobs),
        ]
    )
    binary = build_dir / "cppulse-analyzer"
    dependencies = _dependencies(binary)
    clang = next(
        (name for name in dependencies if re.match(r"libclang-\d+\.so", name)), None
    )
    if clang is None:
        raise NativePackageError(
            "Cannot identify the libclang SONAME and matching resource major"
        )
    clang_major = re.search(r"libclang-(\d+)", clang).group(1)
    libexec = _install_directory(build_dir, "CMAKE_INSTALL_LIBEXECDIR")
    libdir = _install_directory(build_dir, "CMAKE_INSTALL_LIBDIR")
    analyzer_relative = f"{libexec}/cppulse/cppulse-analyzer"
    library_relative = f"{libdir}/cppulse"
    resource_relative = f"share/cppulse/clang/{clang_major}"
    bundled = {
        name: path
        for name, path in dependencies.items()
        if name.startswith(("libfmt.so.", "libspdlog.so."))
    }
    for name in bundled:
        if Path(name).name != name:
            raise NativePackageError(f"Unsafe dependency SONAME: {name}")
    libc, libc_version = platform.libc_ver()
    target = {"platform": "linux", "machine": "x86_64"}
    if libc and libc_version:
        target.update(libc=libc, libc_version=libc_version)
    host = [
        {
            "name": name,
            "constraint": "Required dynamic SONAME available on the tested host",
            "purpose": "Host native runtime dependency",
        }
        for name in sorted(set(dependencies) - set(bundled))
    ]
    host.append(
        {
            "name": "C++ compiler and standard-library headers",
            "constraint": "Compatible with the selected target and compilation context; tested with GCC 14/libstdc++ headers",
            "purpose": "Parse standard C++ includes and run explicitly selected compilation checks",
        }
    )
    if libc:
        host.append(
            {
                "name": libc,
                "constraint": f"Validated on {libc_version}; other host versions are unverified",
                "purpose": "Build-host runtime compatibility boundary",
            }
        )
    notes = dict(notices or {})
    with tempfile.TemporaryDirectory(
        prefix=".cppulse-native-", dir=output_dir
    ) as temporary:
        stage = Path(temporary)
        prefix = stage / candidate
        _run([cmake, "--install", str(build_dir), "--prefix", str(prefix)])
        libraries = prefix / library_relative
        libraries.mkdir(parents=True, exist_ok=True)
        for name, source in bundled.items():
            shutil.copy2(source, libraries / name)
        resources = prefix / resource_relative
        resources.mkdir(parents=True, exist_ok=True)
        if any(path.is_symlink() for path in (resource_dir / "include").rglob("*")):
            raise NativePackageError(
                "Resource inputs contain symlinks; supply an explicitly materialized resource tree"
            )
        shutil.copytree(resource_dir / "include", resources / "include")
        license_dir = prefix / "share/licenses/cppulse-native"
        license_dir.mkdir(parents=True)
        project_license = Path(__file__).resolve().parents[1] / "LICENSE"
        shutil.copy2(project_license, license_dir / "cppulse-LICENSE.txt")
        for name, source in bundled.items():
            family, version = re.match(r"lib(fmt|spdlog)\.so\.(.+)", name).groups()
            package_name = f"lib{family}{version}"
            notice = _notice(notes.get(family), [source.parent], package_name)
            shutil.copy2(notice, license_dir / f"{family}-copyright.txt")
        clang_notice = _notice(
            notes.get("clang"), [resource_dir], f"libclang-common-{clang_major}-dev"
        )
        shutil.copy2(clang_notice, license_dir / "clang-builtins-copyright.txt")
        metadata = {
            "version": "1.0.0",
            "tool_version": __version__,
            "target": target,
            "analyzer": analyzer_relative,
            "analyzer_sha256": _sha256(prefix / analyzer_relative),
            "resource_dir": resource_relative,
            "library_dirs": [library_relative],
            "host_requirements": host,
            "limitations": [
                "Only Linux x86_64 on the declared build host has been exercised.",
                "libclang/LLVM, system runtime libraries and compatible C++ standard-library headers are host requirements.",
                "Builtin headers were explicitly selected for this libclang major; other toolchain combinations remain unverified.",
                "Installation metadata and hashes are not producer authentication or analysis evidence.",
            ],
        }
        validate("native_install", metadata)
        metadata_path = prefix / "share/cppulse/native-install.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        verification = _verify_relocation(prefix, metadata, set(bundled))
        (prefix / "share/cppulse/native-verification.json").write_text(
            json.dumps(verification, indent=2) + "\n", encoding="utf-8"
        )
        files = [
            {
                "path": path.relative_to(prefix).as_posix(),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in sorted(prefix.rglob("*"))
            if path.is_file()
        ]
        (prefix / "share/cppulse/native-files.json").write_text(
            json.dumps(
                {
                    "version": "1.0.0",
                    "files": files,
                    "limitations": [
                        "The inventory excludes its own native-files.json entry."
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        archive = stage / final_archive.name
        with tarfile.open(archive, "w:gz") as stream:
            stream.add(prefix, arcname=candidate)
        checksum = _sha256(archive)
        prefix.rename(final_prefix)
        # Hard-link publication refuses an existing archive and exposes full bytes atomically.
        os.link(archive, final_archive)
    checksum_path.write_text(f"{checksum}  {final_archive.name}\n", encoding="ascii")
    return {
        "archive": str(final_archive),
        "prefix": str(final_prefix),
        "manifest": str(final_prefix / "share/cppulse/native-install.json"),
        "sha256": checksum,
        "checksum_file": str(checksum_path),
    }


def main(argv: list[str] | None = None) -> int:
    """Parse local package options; no remote publication operation exists."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--resource-dir",
        type=Path,
        default=os.environ.get("CPPULSE_CLANG_RESOURCE_DIR"),
    )
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--cmake", default="cmake")
    for component in ("fmt", "spdlog", "clang"):
        parser.add_argument(f"--{component}-notice", type=Path)
    args = parser.parse_args(argv)
    if args.resource_dir is None:
        parser.error("--resource-dir or CPPULSE_CLANG_RESOURCE_DIR is required")
    try:
        result = build_package(
            args.build_dir,
            args.output_dir,
            args.resource_dir,
            cmake=args.cmake,
            jobs=args.jobs,
            notices={
                name: getattr(args, f"{name}_notice")
                for name in ("fmt", "spdlog", "clang")
                if getattr(args, f"{name}_notice") is not None
            },
        )
    except (NativePackageError, OSError) as exc:
        parser.exit(1, f"Native package failed: {exc}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
