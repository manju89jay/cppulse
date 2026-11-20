"""Offline candidate asset checks and real isolated-wheel regression.

The small bundle below is explicitly synthetic packaging data. Browser behavior
is qualified separately against the real built dashboard.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType
import zipfile

import pytest

from test_local_tooling import load_script


@pytest.fixture()
def candidate() -> ModuleType:
    return load_script("package_candidate")


@pytest.fixture()
def asset_source(tmp_path: Path) -> tuple[Path, dict]:
    root = tmp_path / "synthetic package source"
    root.mkdir()
    dashboard = root / "dashboard"
    (dashboard / "src").mkdir(parents=True)
    (dashboard / "package.json").write_text('{"fixture":true}\n')
    (dashboard / "package-lock.json").write_text('{"fixture":true}\n')
    (dashboard / "src/App.tsx").write_text("// synthetic source inventory only\n")
    (root / "README.md").write_text("Explicit synthetic packaging fixture.\n")
    (root / "LICENSE").write_text("Synthetic fixture data only.\n")
    (root / "pyproject.toml").write_text(
        '[build-system]\nrequires=["setuptools==75.8.0","wheel==0.45.1"]\n'
        'build-backend="setuptools.build_meta"\n'
        '[project]\nname="cppulse"\nversion="0.0.0"\nreadme="README.md"\n'
        '[tool.setuptools.packages.find]\nwhere=["python"]\n'
        '[tool.setuptools.package-data]\ncppulse=["data/dashboard/**/*"]\n'
    )
    package = root / "python/cppulse"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('"""Synthetic wheel-content fixture."""\n')
    target = package / "data/dashboard"
    (target / "assets").mkdir(parents=True)
    (target / "index.html").write_text('<script src="assets/current.js"></script>\n')
    (target / "assets/current.js").write_text("// synthetic current asset\n")
    (target / "assets/current.css").write_text("body { color: black; }\n")
    builder = load_script("build_dashboard_assets")
    manifest = {
        "version": "1.0.0",
        "sources": builder.source_inventory(root),
        "files": builder.asset_inventory(target),
        "limitations": ["Synthetic packaging fixture; not a browser verification."],
    }
    (target / "asset-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return root, manifest


def test_candidate_preflight_checks_sources_and_payload_without_node(
    candidate: ModuleType, asset_source: tuple[Path, dict], monkeypatch
) -> None:
    root, expected = asset_source

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Asset verification must not invoke Node or any subprocess"
        )

    monkeypatch.setattr(subprocess, "run", forbidden)
    assert candidate.verify_dashboard_assets(root) == expected


@pytest.mark.parametrize("change", ["source", "asset", "missing-index"])
def test_candidate_rejects_stale_or_incomplete_assets(
    candidate: ModuleType, asset_source: tuple[Path, dict], change: str
) -> None:
    root, _ = asset_source
    if change == "source":
        (root / "dashboard/src/App.tsx").write_text("// changed after bundle build\n")
    elif change == "asset":
        (root / "python/cppulse/data/dashboard/assets/current.js").write_text(
            "// changed package bytes\n"
        )
    else:
        (root / "python/cppulse/data/dashboard/index.html").unlink()
    with pytest.raises(candidate.CandidateError, match="[Dd]ashboard"):
        candidate.verify_dashboard_assets(root)


def test_invalid_assets_fail_before_candidate_output_or_wheel_build(
    candidate: ModuleType, asset_source: tuple[Path, dict], tmp_path: Path, monkeypatch
) -> None:
    root, _ = asset_source
    (root / "python/cppulse/data/dashboard/asset-manifest.json").unlink()
    archive = tmp_path / "synthetic-native.tar.gz"
    archive.write_bytes(b"synthetic native metadata is supplied by this focused test")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    output = tmp_path / "candidate"
    monkeypatch.setattr(
        candidate,
        "native_metadata",
        lambda path: {"tool_version": "0.0.0"},
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid assets must prevent every build command")

    monkeypatch.setattr(candidate, "_command", forbidden)
    with pytest.raises(candidate.CandidateError, match="[Dd]ashboard"):
        candidate.build_candidate(archive, wheelhouse, output, root=root)
    assert not output.exists()


def write_wheel(root: Path, wheel: Path, *, change: str = "") -> None:
    """Write data-only wheel members for corruption/missing-payload cases."""
    assets = root / "python/cppulse/data/dashboard"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path in assets.rglob("*"):
            if path.is_file():
                if change == "missing-index" and path.name == "index.html":
                    continue
                data = path.read_bytes()
                if change == "corrupt-js" and path.suffix == ".js":
                    data += b"// corruption\n"
                archive.writestr(
                    "cppulse/data/dashboard/" + path.relative_to(assets).as_posix(),
                    data,
                )
        if change == "stale-extra":
            archive.writestr("cppulse/data/dashboard/assets/deleted.js", "// old cache")


@pytest.mark.parametrize("change", ["", "missing-index", "corrupt-js", "stale-extra"])
def test_wheel_must_contain_exact_checked_bundle(
    candidate: ModuleType,
    asset_source: tuple[Path, dict],
    tmp_path: Path,
    change: str,
) -> None:
    root, manifest = asset_source
    wheel = tmp_path / "synthetic.whl"
    write_wheel(root, wheel, change=change)
    manifest_sha = hashlib.sha256(
        (root / "python/cppulse/data/dashboard/asset-manifest.json").read_bytes()
    ).hexdigest()
    if change:
        with pytest.raises(candidate.CandidateError, match="[Dd]ashboard"):
            candidate.verify_wheel_dashboard(wheel, manifest, manifest_sha)
    else:
        candidate.verify_wheel_dashboard(wheel, manifest, manifest_sha)


def test_actual_isolated_wheel_cannot_inherit_deleted_asset_cache(
    candidate: ModuleType, asset_source: tuple[Path, dict], tmp_path: Path
) -> None:
    root, manifest = asset_source
    stale = root / "build/lib/cppulse/data/dashboard/assets/deleted.js"
    stale.parent.mkdir(parents=True)
    stale.write_text("// synthetic stale backend cache from a prior build\n")
    pycache = root / "python/cppulse/__pycache__"
    pycache.mkdir()
    (pycache / "fake.pyc").write_bytes(b"synthetic cache")
    build_source = tmp_path / "isolated build input"
    inventory = candidate.prepare_build_source(root, build_source)
    assert not (build_source / "build").exists()
    assert not (build_source / "python/cppulse/__pycache__").exists()
    assert "python/cppulse/__init__.py" in {row["path"] for row in inventory}
    output = tmp_path / "wheel-output"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(output),
            str(build_source),
        ],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    wheel = next(output.glob("*.whl"))
    manifest_sha = hashlib.sha256(
        (root / "python/cppulse/data/dashboard/asset-manifest.json").read_bytes()
    ).hexdigest()
    candidate.verify_wheel_dashboard(wheel, manifest, manifest_sha)
    assert stale.is_file(), "Existing local build data must be preserved"


def test_isolated_build_refuses_source_symlinks(
    candidate: ModuleType, asset_source: tuple[Path, dict], tmp_path: Path
) -> None:
    root, _ = asset_source
    secret = tmp_path / "outside.txt"
    secret.write_text("Synthetic outside data must not enter a package")
    (root / "python/cppulse/outside.txt").symlink_to(secret)
    with pytest.raises(candidate.CandidateError, match="[Ss]ymlink"):
        candidate.prepare_build_source(root, tmp_path / "copy")


def test_build_copy_destination_cannot_reenter_selected_python_inputs(
    candidate: ModuleType, asset_source: tuple[Path, dict], monkeypatch
) -> None:
    root, _ = asset_source
    destination = root / "python/nested-isolated-build"

    def forbidden(*args, **kwargs):
        raise AssertionError("Recursive source copy must be rejected before copytree")

    monkeypatch.setattr(candidate.shutil, "copytree", forbidden)
    with pytest.raises(candidate.CandidateError, match="[Pp]ython input"):
        candidate.prepare_build_source(root, destination)
    assert not destination.exists()


def test_candidate_output_cannot_reenter_selected_python_inputs(
    candidate: ModuleType,
    asset_source: tuple[Path, dict],
    tmp_path: Path,
    monkeypatch,
) -> None:
    root, _ = asset_source
    archive = tmp_path / "synthetic-native.tar.gz"
    archive.write_bytes(b"synthetic metadata supplied by this boundary test")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    output = root / "python/nested-candidate"
    monkeypatch.setattr(
        candidate, "native_metadata", lambda path: {"tool_version": "0.0.0"}
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Unsafe output must be rejected before allocation/source scan"
        )

    monkeypatch.setattr(candidate, "source_state", forbidden)
    with pytest.raises(candidate.CandidateError, match="[Pp]ython input"):
        candidate.build_candidate(archive, wheelhouse, output, root=root)
    assert not output.exists()


@pytest.mark.parametrize("subdirectory", ["dashboard", "docs", "scripts"])
def test_source_identity_cannot_hide_real_inputs_as_candidate_output(
    candidate: ModuleType, asset_source: tuple[Path, dict], subdirectory: str
) -> None:
    root, _ = asset_source
    with pytest.raises(candidate.CandidateError, match="[Ii]nput|output/|review/"):
        candidate.source_state(root, root / subdirectory)
