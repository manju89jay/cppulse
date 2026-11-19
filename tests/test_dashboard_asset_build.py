"""Distribution preflight rejects stale/corrupt assets without invoking Node."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_dashboard_assets import (
    MANIFEST,
    asset_inventory,
    build_assets,
    source_inventory,
    verify_assets,
)


@pytest.fixture()
def selected_bundle(tmp_path: Path) -> tuple[Path, Path]:
    """Create clearly synthetic selected source/output bytes, not a built app."""
    source = tmp_path / "project"
    (source / "dashboard/src").mkdir(parents=True)
    (source / "dashboard/src/App.tsx").write_text("// synthetic source\n")
    (source / "dashboard/package-lock.json").write_text("{}\n")
    (source / "dashboard/index.html").write_text("<html>source shell</html>")
    (source / "dashboard/vite.config.ts").write_text("// synthetic config\n")
    assets = tmp_path / "bundle"
    (assets / "assets").mkdir(parents=True)
    (assets / "index.html").write_text("<html>synthetic retained shell</html>")
    (assets / "assets/app.js").write_text("// synthetic JS\n")
    (assets / "assets/app.css").write_text("/* synthetic CSS */\n")
    (assets / MANIFEST).write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "sources": source_inventory(source),
                "files": asset_inventory(assets),
            }
        )
    )
    return source, assets


def test_check_is_read_only_and_requires_no_node(
    selected_bundle: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    source, assets = selected_bundle
    before = {
        str(path): path.read_bytes() for path in assets.rglob("*") if path.is_file()
    }

    def reject(*args: object, **kwargs: object) -> None:
        raise AssertionError("Verification must not execute build tools")

    monkeypatch.setattr("scripts.build_dashboard_assets.subprocess.run", reject)
    assert len(verify_assets(source, assets)["files"]) == 3
    assert {
        str(path): path.read_bytes() for path in assets.rglob("*") if path.is_file()
    } == before


def test_source_change_makes_bundle_stale(selected_bundle: tuple[Path, Path]) -> None:
    source, assets = selected_bundle
    (source / "dashboard/src/App.tsx").write_text("// changed source!!\n")
    with pytest.raises(ValueError, match="stale"):
        verify_assets(source, assets)


def test_payload_change_is_detected(selected_bundle: tuple[Path, Path]) -> None:
    source, assets = selected_bundle
    (assets / "assets/app.js").write_text("// corrupted JS\n")
    with pytest.raises(ValueError, match="disagree"):
        verify_assets(source, assets)


def test_missing_index_or_symlink_cannot_be_packaged(
    selected_bundle: tuple[Path, Path]
) -> None:
    source, assets = selected_bundle
    (assets / "index.html").unlink()
    with pytest.raises(ValueError, match="index"):
        verify_assets(source, assets)
    (assets / "index.html").symlink_to(source / "dashboard/index.html")
    with pytest.raises(ValueError, match="Symlink"):
        verify_assets(source, assets)


def test_build_refuses_to_replace_unowned_directory(tmp_path: Path) -> None:
    destination = tmp_path / "not-generated"
    destination.mkdir()
    marker = destination / "important.txt"
    marker.write_text("preserve this file")
    with pytest.raises(ValueError, match="Refusing"):
        build_assets(tmp_path, destination)
    assert marker.read_text() == "preserve this file"


def test_rebuild_retains_complete_notice_as_checked_source(
    selected_bundle: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A controlled build transport must retain the entire attribution input."""
    source, assets = selected_bundle
    notice = source / "dashboard/src/third-party-notices.txt"
    body = b"Synthetic package attribution\nComplete synthetic license body.\n"
    notice.write_bytes(body)

    def produce(command: list[str], **kwargs: object) -> None:
        output = Path(command[-1])
        (output / "assets").mkdir(parents=True)
        (output / "index.html").write_text("<html>new controlled output</html>")
        (output / "assets/app.js").write_text("// controlled build JS\n")
        (output / "assets/app.css").write_text("/* controlled build CSS */\n")

    monkeypatch.setattr("scripts.build_dashboard_assets.subprocess.run", produce)
    manifest = build_assets(source, assets)
    assert (assets / "assets/third-party-notices.txt").read_bytes() == body
    assert any(
        row["path"] == "src/third-party-notices.txt" for row in manifest["sources"]
    )
    assert any(
        row["path"] == "assets/third-party-notices.txt" for row in manifest["files"]
    )
    assert verify_assets(source, assets) == manifest
    notice.write_bytes(body + b"Changed attribution input.\n")
    with pytest.raises(ValueError, match="stale"):
        verify_assets(source, assets)


def test_missing_notice_refuses_before_tools_or_output_replacement(
    selected_bundle: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rebuild cannot silently discard the previously retained license."""
    source, assets = selected_bundle
    before = {
        str(path): path.read_bytes() for path in assets.rglob("*") if path.is_file()
    }

    def reject(*args: object, **kwargs: object) -> None:
        raise AssertionError("Missing legal input must refuse before build tools")

    monkeypatch.setattr("scripts.build_dashboard_assets.subprocess.run", reject)
    with pytest.raises(ValueError, match="regular asset/source file"):
        build_assets(source, assets)
    assert {
        str(path): path.read_bytes() for path in assets.rglob("*") if path.is_file()
    } == before
