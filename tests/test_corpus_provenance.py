"""Pinned corpus runs must not silently analyze locally changed checkouts."""

from __future__ import annotations
from pathlib import Path
import subprocess
import pytest
from scripts.run_real_corpus import pinned_revision


@pytest.fixture
def checkout(tmp_path: Path) -> tuple[Path, str]:
    """Create an explicit automation-only local Git input using actual time."""

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(tmp_path), *args], text=True
        ).strip()

    git("init", "-q")
    (tmp_path / "source.cpp").write_text("int value = 0;\n")
    git("add", "source.cpp")
    git(
        "-c",
        "user.name=cppulse Test Automation",
        "-c",
        "user.email=tests@example.invalid",
        "commit",
        "-qm",
        "Synthetic test input",
    )
    return tmp_path, git("rev-parse", "HEAD")


def test_clean_locked_source_is_accepted(checkout: tuple[Path, str]) -> None:
    root, revision = checkout
    assert pinned_revision(root, revision) == revision


def test_dirty_tracked_source_is_rejected(checkout: tuple[Path, str]) -> None:
    root, revision = checkout
    (root / "source.cpp").write_text("int value = 1;\n")
    with pytest.raises(RuntimeError, match="local changes"):
        pinned_revision(root, revision)


def test_untracked_source_is_rejected(checkout: tuple[Path, str]) -> None:
    root, revision = checkout
    (root / "extra.cpp").write_text("int extra = 2;\n")
    with pytest.raises(RuntimeError, match="local changes"):
        pinned_revision(root, revision)
