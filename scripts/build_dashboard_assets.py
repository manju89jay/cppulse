"""Build checked local dashboard assets for the installed wheel; never publish."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "python/cppulse/data/dashboard"
MANIFEST = "asset-manifest.json"


def digest(path: Path) -> str:
    """Hash one selected regular file's exact bytes."""
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular asset/source file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_inventory(root: Path) -> list[dict[str, str]]:
    """Select build configuration, dependency lock and dashboard source bytes."""
    dashboard = root / "dashboard"
    selected = [
        *dashboard.glob("*.json"),
        *dashboard.glob("*.cjs"),
        dashboard / "index.html",
        dashboard / "vite.config.ts",
        *dashboard.joinpath("src").rglob("*"),
    ]
    return [
        {"path": path.relative_to(dashboard).as_posix(), "sha256": digest(path)}
        for path in sorted(set(selected))
        if path.is_file() or path.is_symlink()
    ]


def asset_inventory(directory: Path) -> list[dict[str, Any]]:
    """Inventory a bounded regular production bundle, excluding its descriptor."""
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink is not a packaged dashboard asset: {path}")
        if not path.is_file() or path.name == MANIFEST:
            continue
        size = path.stat().st_size
        if size > 10 * 1024 * 1024:
            raise ValueError("Dashboard asset exceeds the selected 10 MiB bound")
        files.append(
            {
                "path": path.relative_to(directory).as_posix(),
                "sha256": digest(path),
                "size_bytes": size,
            }
        )
    names = {row["path"] for row in files}
    if (
        len(files) > 64
        or "index.html" not in names
        or not any(name.endswith(".js") for name in names)
        or not any(name.endswith(".css") for name in names)
    ):
        raise ValueError(
            "Expected a bounded dashboard index, JavaScript and CSS bundle"
        )
    return files


def verify_assets(root: Path = ROOT, destination: Path = DESTINATION) -> dict[str, Any]:
    """Check bundled bytes and selected current sources without invoking Node."""
    if destination.is_symlink():
        raise ValueError("Dashboard asset directory cannot be a symlink")
    descriptor = destination / MANIFEST
    if descriptor.stat().st_size > 1024 * 1024:
        raise ValueError("Dashboard asset manifest exceeds its 1 MiB bound")
    manifest = json.loads(descriptor.read_text(encoding="utf-8"))
    if manifest.get("version") != "1.0.0" or manifest.get(
        "sources"
    ) != source_inventory(root):
        raise ValueError(
            "Dashboard assets are stale for the selected source/lock bytes; run scripts/build_dashboard_assets.py"
        )
    if manifest.get("files") != asset_inventory(destination):
        raise ValueError("Dashboard packaged bytes disagree with the asset manifest")
    return manifest


def build_assets(root: Path = ROOT, destination: Path = DESTINATION) -> dict[str, Any]:
    """Compile locally, check the complete output, then replace owned assets."""
    if (
        destination.is_symlink()
        or destination.exists()
        and not (destination / MANIFEST).is_file()
    ):
        raise ValueError(
            "Refusing to replace a directory without our dashboard asset manifest"
        )
    before = source_inventory(root)
    with tempfile.TemporaryDirectory(prefix="cppulse-dashboard-") as temporary:
        built = Path(temporary) / "dist"
        subprocess.run(
            ["npm", "run", "build", "--", "--outDir", str(built)],
            cwd=root / "dashboard",
            check=True,
        )
        files = asset_inventory(built)
        if source_inventory(root) != before:
            raise ValueError("Dashboard source changed during the production build")
        manifest = {
            "version": "1.0.0",
            "sources": before,
            "files": files,
            "limitations": [
                "Local production bundle; build tooling is not needed to serve these retained assets. This manifest is not producer authentication."
            ],
        }
        (built / MANIFEST).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(built, destination)
    return verify_assets(root, destination)


def main() -> None:
    """Build explicitly or verify retained assets with no Node invocation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        manifest = verify_assets() if args.check else build_assets()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Dashboard assets unavailable: {error}\n")
    print(
        json.dumps(
            {
                "status": "verified",
                "directory": str(DESTINATION),
                "files": len(manifest["files"]),
            }
        )
    )


if __name__ == "__main__":
    main()
