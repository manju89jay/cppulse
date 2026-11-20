#!/usr/bin/env python3
"""Prepare a local candidate from a wheel and native archive; never publish."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.parser import Parser
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from typing import Any
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


class CandidateError(RuntimeError):
    """The local artifact cannot honestly be called a prepared candidate."""


def _validate_output(root: Path, output: Path) -> None:
    root, output = root.resolve(), output.resolve()
    if root.is_relative_to(output):
        raise CandidateError(
            "Candidate output cannot be the checkout root or its ancestor"
        )
    for name in ("python", "dashboard"):
        if output.is_relative_to(root / name):
            raise CandidateError(
                f"Candidate output cannot overlap selected {name.title()} inputs"
            )
    if output.is_relative_to(root) and not any(
        output.is_relative_to(root / name) for name in ("output", "review")
    ):
        raise CandidateError(
            "Inside the checkout, candidate output must be under output/ or review/; use an external directory otherwise"
        )


def verify_dashboard_assets(root: Path) -> dict[str, Any]:
    """Check the released asset producer without invoking its Node build path."""
    path = Path(__file__).with_name("build_dashboard_assets.py")
    spec = importlib.util.spec_from_file_location("cppulse_candidate_assets", path)
    if spec is None or spec.loader is None:
        raise CandidateError("Dashboard asset verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.verify_assets(root, root / "python/cppulse/data/dashboard")
    except (OSError, ValueError) as error:
        raise CandidateError(f"Dashboard assets failed preflight: {error}") from error


def verify_wheel_dashboard(
    wheel: Path, manifest: dict[str, Any], manifest_sha256: str
) -> None:
    """Require the exact checked bundle, including no deleted cached assets."""
    prefix = "cppulse/data/dashboard/"
    expected = {prefix + row["path"] for row in manifest["files"]}
    expected.add(prefix + "asset-manifest.json")
    with zipfile.ZipFile(wheel) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.startswith(prefix) and not name.endswith("/")
        ]
        if len(names) != len(set(names)) or set(names) != expected:
            raise CandidateError(
                "Dashboard wheel payload is incomplete or has stale extras"
            )
        descriptor = archive.read(prefix + "asset-manifest.json")
        if hashlib.sha256(descriptor).hexdigest() != manifest_sha256:
            raise CandidateError("Dashboard wheel manifest differs from checked bytes")
        for row in manifest["files"]:
            content = archive.read(prefix + row["path"])
            if (
                len(content) != row["size_bytes"]
                or hashlib.sha256(content).hexdigest() != row["sha256"]
            ):
                raise CandidateError("Dashboard wheel asset differs from checked bytes")


def prepare_build_source(root: Path, destination: Path) -> list[dict[str, Any]]:
    """Copy declared Python build inputs into a clean private backend tree.

    Existing checkout build caches are preserved. They must not supply deleted
    modules or old hashed JavaScript to a newly built wheel.
    """
    if destination.exists() or destination.is_symlink():
        raise CandidateError("Isolated build destination must not already exist")
    for name in ("python", "dashboard"):
        if destination.resolve().is_relative_to(root.resolve() / name):
            raise CandidateError(
                f"Build destination cannot overlap selected {name.title()} inputs"
            )
    python = root / "python"
    if python.is_symlink() or not python.is_dir():
        raise CandidateError("Python package input is missing or a symlink")
    for path in python.rglob("*"):
        parts = path.relative_to(python).parts
        if any(part == "__pycache__" or part.endswith(".egg-info") for part in parts):
            continue
        if path.is_symlink():
            raise CandidateError(f"Symlink is not a candidate build input: {path}")
    names = ["pyproject.toml", "README.md", "LICENSE"]
    names += [
        name
        for name in ["setup.cfg", "setup.py", "MANIFEST.in"]
        if (root / name).exists()
    ]
    for name in names:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise CandidateError(f"Build input is missing or a symlink: {name}")
    destination.mkdir(parents=True)
    for name in names:
        shutil.copy2(root / name, destination / name)
    shutil.copytree(
        python,
        destination / "python",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    return [
        {
            "path": path.relative_to(destination).as_posix(),
            "sha256": digest(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    ]


def digest(path: Path) -> str:
    """Hash exact artifact bytes without changing timestamps or authorship."""
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def wheel_metadata(path: Path) -> dict[str, Any]:
    """Read identity/dependencies locally and reject remote dependency references."""
    with zipfile.ZipFile(path) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
        ]
        if len(names) != 1:
            raise CandidateError(f"Expected one distribution METADATA in {path.name}")
        metadata = Parser().parsestr(archive.read(names[0]).decode("utf-8"))
    name = metadata.get("Name")
    version = metadata.get("Version")
    if not name or not version:
        raise CandidateError(f"Missing distribution identity: {path.name}")
    requires = metadata.get_all("Requires-Dist", [])
    for requirement in requires:
        if Requirement(requirement).url:
            raise CandidateError(
                f"Remote/direct dependency is not permitted in offline candidate resolution: {requirement}"
            )
    return {
        "name": canonicalize_name(name, validate=True),
        "version": version,
        "requires": requires,
        "requires_python": metadata.get("Requires-Python"),
        "license": metadata.get("License-Expression")
        or metadata.get("License")
        or "Not declared in wheel metadata",
        "filename": path.name,
        "sha256": digest(path),
        "size_bytes": path.stat().st_size,
    }


def source_state(root: Path, output: Path | None = None) -> dict[str, Any]:
    """Record HEAD plus tracked diff and untracked source bytes without ref writes."""
    if output is not None:
        _validate_output(root, output)

    def git(*arguments: str) -> bytes:
        return subprocess.check_output(["git", *arguments], cwd=root)

    revision = git("rev-parse", "HEAD").decode().strip()
    diff = git("diff", "--binary", "HEAD")
    files = git("ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")
    untracked: list[dict[str, str]] = []
    for name in sorted(set(files)):
        if not name or name.startswith(("review/", "output/")):
            continue
        path = root / name
        if output is not None and path.resolve().is_relative_to(output.resolve()):
            continue
        if path.is_symlink():
            value = hashlib.sha256(os.readlink(path).encode()).hexdigest()
        elif path.is_file():
            if not path.resolve().is_relative_to(root.resolve()):
                raise CandidateError(f"Source path escapes checkout: {name}")
            value = digest(path)
        else:
            continue
        untracked.append({"path": name, "sha256": value})
    result = {
        "head": revision,
        "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "untracked_sources": untracked,
    }
    result["worktree_digest"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result


def core_inventory(
    wheel_dir: Path, project: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Verify the resolved closure uses exactly required core distributions."""
    items = [wheel_metadata(path) for path in sorted(wheel_dir.glob("*.whl"))]
    by_name = {item["name"]: item for item in items}
    if len(by_name) != len(items):
        raise CandidateError(
            "Multiple wheel versions selected for the same distribution"
        )
    package = canonicalize_name(project["name"])
    if package not in by_name or by_name[package]["version"] != project["version"]:
        raise CandidateError(
            "Resolved wheel does not match the requested project version"
        )
    required = {package}
    pending = [package]
    edges: dict[str, list[str]] = {}
    while pending:
        name = pending.pop()
        item = by_name[name]
        dependencies = []
        for value in item["requires"]:
            requirement = Requirement(value)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            dependency = canonicalize_name(requirement.name)
            if (
                dependency not in by_name
                or by_name[dependency]["version"] not in requirement.specifier
            ):
                raise CandidateError(f"Missing/incompatible core dependency: {value}")
            dependencies.append(dependency)
            if dependency not in required:
                required.add(dependency)
                pending.append(dependency)
        edges[name] = sorted(set(dependencies))
    if set(by_name) != required:
        raise CandidateError(
            "Resolved wheel directory includes unrelated optional/development packages"
        )
    graph = [
        {
            "ref": f'pkg:pypi/{name}@{by_name[name]["version"]}',
            "dependsOn": [
                f'pkg:pypi/{child}@{by_name[child]["version"]}' for child in children
            ],
        }
        for name, children in sorted(edges.items())
    ]
    return items, graph


def write_lock(items: list[dict[str, Any]], target: Path) -> None:
    """Pin the actual environment-specific core closure and exact wheel hashes."""
    lines = [
        "# Resolved core-only closure; exact local wheels, current Python/platform.",
        "# This is not a universal lock for other platforms or optional extras.",
    ]
    lines.extend(
        f'{item["name"]}=={item["version"]} --hash=sha256:{item["sha256"]}'
        for item in sorted(items, key=lambda item: item["name"])
    )
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def native_metadata(archive_path: Path) -> dict[str, Any]:
    """Inspect installation metadata without extracting or executing the archive."""
    with tarfile.open(archive_path, "r:*") as archive:
        matches = [
            member
            for member in archive.getmembers()
            if member.name.endswith("/share/cppulse/native-install.json")
            and member.isfile()
        ]
        if len(matches) != 1 or matches[0].size > 1024 * 1024:
            raise CandidateError(
                "Expected one bounded native-install.json in the native archive"
            )
        stream = archive.extractfile(matches[0])
        if stream is None:
            raise CandidateError("Native installation metadata could not be read")
        metadata = json.load(stream)
    if (
        metadata.get("version") != "1.0.0"
        or not metadata.get("tool_version")
        or not metadata.get("target")
    ):
        raise CandidateError("Unsupported native installation metadata")
    target = metadata["target"]
    if not isinstance(target, dict) or any(
        not isinstance(target.get(key), str)
        or re.fullmatch(r"[A-Za-z0-9_]+", target[key]) is None
        for key in ("platform", "machine")
    ):
        raise CandidateError("Native target requires safe platform and machine labels")
    return metadata


def _licenses(wheel_dir: Path, notices: Path, items: list[dict[str, Any]]) -> None:
    for item in items:
        with zipfile.ZipFile(wheel_dir / item["filename"]) as archive:
            for name in archive.namelist():
                parts = Path(name).parts
                if not parts or name.endswith("/"):
                    continue
                basename = parts[-1].lower()
                if not (
                    ".dist-info/licenses/" in name.lower()
                    or basename.startswith(("license", "copying", "notice"))
                ):
                    continue
                if (
                    Path(name).is_absolute()
                    or ".." in parts
                    or "\\" in name
                    or ":" in name
                ):
                    raise CandidateError("Unsafe license path inside wheel")
                destination = notices / item["name"] / Path(name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(name))


def _command(argv: list[str], cwd: Path, log: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(
            argv,
            cwd=cwd,
            stdout=stream,
            stderr=subprocess.STDOUT,
            shell=False,
            check=False,
        )
    if result.returncode:
        raise CandidateError(f"Local command exited {result.returncode}; see {log}")


def build_candidate(
    native_archive: Path,
    wheelhouse: Path,
    output_dir: Path,
    *,
    root: Path = ROOT,
    expected_version: str | None = None,
) -> Path:
    """Build and inventory a local candidate without installs, network or publication."""
    python = sys.executable
    root = root.resolve()
    native_archive = native_archive.resolve(strict=True)
    wheelhouse = wheelhouse.resolve(strict=True)
    output_dir = output_dir.resolve()
    if root.is_relative_to(output_dir):
        raise CandidateError(
            "Candidate output cannot be the checkout root or its ancestor"
        )
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    if expected_version is not None and expected_version != project["version"]:
        raise CandidateError("Requested version differs from pyproject.toml")
    if config["build-system"]["build-backend"] != "setuptools.build_meta":
        raise CandidateError("Only the declared local setuptools backend is supported")
    for wheel in wheelhouse.glob("*.whl"):
        wheel_metadata(wheel)
    native = native_metadata(native_archive)
    if native["tool_version"] != project["version"]:
        raise CandidateError("Native and Python candidate versions disagree")
    _validate_output(root, output_dir)
    dashboard = verify_dashboard_assets(root)
    dashboard_manifest_sha = digest(
        root / "python/cppulse/data/dashboard/asset-manifest.json"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    before = source_state(root, output_dir)
    name = f'cppulse-{project["version"]}-{native["target"]["platform"]}-{native["target"]["machine"]}-candidate'
    final = output_dir / name
    if final.exists():
        raise CandidateError(
            f"Candidate already exists; use another output directory: {final}"
        )
    stage = Path(tempfile.mkdtemp(prefix=".cppulse-candidate-", dir=output_dir))
    build_source = stage / "build-source"
    build_inputs = prepare_build_source(root, build_source)
    built = stage / "build-output"
    build_argv = [
        python,
        "-m",
        "build",
        "--wheel",
        "--no-isolation",
        "--outdir",
        str(built),
        str(build_source),
    ]
    _command(build_argv, build_source, stage / "logs/wheel-build.log")
    wheels = list(built.glob("*.whl"))
    if len(wheels) != 1:
        raise CandidateError("Wheel build did not produce exactly one wheel")
    wheel_metadata(wheels[0])
    verify_wheel_dashboard(wheels[0], dashboard, dashboard_manifest_sha)
    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_headers = [
            name for name in archive.namelist() if name.endswith(".dist-info/WHEEL")
        ]
        if len(wheel_headers) != 1:
            raise CandidateError("Built wheel has no unique WHEEL metadata")
        wheel_info = Parser().parsestr(archive.read(wheel_headers[0]).decode("utf-8"))
        if (
            wheel_info.get("Root-Is-Purelib", "").lower() != "true"
            or any(
                not value.endswith("-none-any")
                for value in wheel_info.get_all("Tag", [])
            )
            or not wheel_info.get_all("Tag")
        ):
            raise CandidateError(
                "Python candidate must be a pure, platform-independent wheel"
            )
    closure = stage / "core-wheelhouse"
    resolve_argv = [
        python,
        "-m",
        "pip",
        "--isolated",
        "download",
        "--no-cache-dir",
        "--no-index",
        "--find-links",
        str(wheelhouse),
        "--only-binary=:all:",
        "--dest",
        str(closure),
        str(wheels[0]),
    ]
    _command(resolve_argv, root, stage / "logs/core-resolution.log")
    items, graph = core_inventory(closure, project)
    shutil.rmtree(built)
    shutil.rmtree(build_source)
    write_lock(items, stage / "core-requirements.lock")
    _licenses(closure, stage / "notices/core", items)
    shutil.copy2(root / "LICENSE", stage / "LICENSE")
    native_dir = stage / "native"
    native_dir.mkdir()
    shutil.copy2(native_archive, native_dir / native_archive.name)
    now = datetime.now(timezone.utc).isoformat()
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": now,
            "component": {
                "type": "application",
                "name": project["name"],
                "version": project["version"],
            },
        },
        "components": [
            {
                "type": "library",
                "name": item["name"],
                "version": item["version"],
                "bom-ref": f'pkg:pypi/{item["name"]}@{item["version"]}',
                "purl": f'pkg:pypi/{item["name"]}@{item["version"]}',
                "hashes": [{"alg": "SHA-256", "content": item["sha256"]}],
                "licenses": [{"license": {"name": item["license"]}}],
            }
            for item in items
        ],
        "dependencies": graph,
    }
    (stage / "core-sbom.cdx.json").write_text(
        json.dumps(sbom, indent=2) + "\n", encoding="utf-8"
    )
    (stage / "core-dependencies.json").write_text(
        json.dumps(items, indent=2) + "\n", encoding="utf-8"
    )
    after = source_state(root, output_dir)
    if before["worktree_digest"] != after["worktree_digest"]:
        raise CandidateError(
            "Source changed during candidate preparation; rerun on a stable working tree"
        )
    manifest = {
        "version": "1.0.0",
        "candidate_status": "prepared",
        "tool_version": project["version"],
        "created_at": now,
        "source": before,
        "build_inputs": build_inputs,
        "dashboard": {
            "manifest_sha256": dashboard_manifest_sha,
            "files": dashboard["files"],
            "node_required_to_serve": False,
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": sys.platform,
            "machine": platform.machine(),
        },
        "native": {
            "artifact": "native/" + native_archive.name,
            "sha256": digest(native_archive),
            "metadata": native,
        },
        "core_distributions": len(items),
        "commands": [build_argv, resolve_argv],
        "verification": {
            "wheel_build": "passed",
            "offline_core_resolution": "passed",
            "checked_dashboard_payload": "passed",
            "installed_dashboard": "not_run_by_candidate_builder",
            "installed_smoke": "not_run_by_candidate_builder",
            "compose": "not_run_by_candidate_builder",
        },
        "limitations": [
            "Preparation is not publication or proof of installed behavior.",
            "Core wheel closure and hashes apply to this Python/platform only; optional ML/PDF/web extras are excluded.",
            "Native target and host dependencies are declared in its manifest; other operating systems remain unverified.",
            "Source identities are descriptive and hashes do not authenticate the producer.",
            "Native archive identity is recorded; its source binding must be reviewed with native build evidence.",
        ],
    }
    (stage / "candidate.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (stage / "SUPPORT.md").write_text(
        f"""# Candidate support matrix\n\nPython core declares {project["requires-python"]}; this closure was resolved for Python {platform.python_version()} on {sys.platform}/{platform.machine()}.\n\nNative target: {native["target"]}. Host requirements and limits are in candidate.json.\n\nPython 3.11 is in the declared package range but is not established by this environment-specific closure. Windows, macOS and alternative toolchain combinations are not established by this candidate. Optional ML/PDF/web extras are not included. Native libclang/LLVM and compatible compiler standard-library headers remain host requirements.\n\nWheel build and local dependency resolution passed. Installed and Compose verification are separate checks.\n""",
        encoding="utf-8",
    )
    (stage / "INSTALL_UPGRADE_ROLLBACK.md").write_text(
        """# Local install and rollback\n\nVerify SHA256SUMS before use. Create a new Python virtual environment, then install the exact local core closure:\n\n    python -m pip install --no-index --find-links core-wheelhouse --require-hashes -r core-requirements.lock\n\nExtract the native archive under a new versioned prefix, satisfy its declared host requirements, and set CPPULSE_NATIVE_PREFIX to that extracted prefix. Run cppulse doctor and an explicit analysis/report smoke test outside the source checkout. No test commands are run merely by reading project configuration.\n\nFor an upgrade, retain the previous prefix, virtual environment, candidate artifacts and outputs; install the new candidate alongside them and verify before selecting it. To roll back, reactivate the previous environment/prefix. Do not silently migrate or overwrite old output/contracts. No automatic self-update, remote publication or deployment is performed by this package.\n""",
        encoding="utf-8",
    )
    inventory = [
        {
            "path": str(path.relative_to(stage)),
            "sha256": digest(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(stage.rglob("*"))
        if path.is_file()
    ]
    (stage / "files.json").write_text(
        json.dumps(
            {
                "files": inventory,
                "limitations": [
                    "Inventory excludes its own files.json and SHA256SUMS entries."
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    checksums = [
        f"{digest(path)}  {path.relative_to(stage).as_posix()}"
        for path in sorted(stage.rglob("*"))
        if path.is_file()
    ]
    (stage / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="ascii")
    stage.rename(final)
    return final


def main(argv: list[str] | None = None) -> int:
    """Prepare local files only; all publishing/install operations are separate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-archive", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    try:
        result = build_candidate(
            args.native_archive,
            args.wheelhouse,
            args.output_dir,
            expected_version=args.version,
        )
    except (CandidateError, OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Candidate preparation failed: {error}\n")
    print(json.dumps({"candidate": str(result), "status": "prepared"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
