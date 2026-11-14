"""Tests for src/commit_utils.py — robust history traversal helpers."""

from __future__ import annotations

from pathlib import Path

import git

from src.commit_utils import changed_files

_DEFAULT = git.Actor("Dev", "dev@example.com")


def _init_repo(tmp_path: Path) -> git.Repo:
    """Create a git repo with gpgsign disabled."""
    repo = git.Repo.init(str(tmp_path))
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Dev")
        cfg.set_value("user", "email", "dev@example.com")
        cfg.set_value("commit", "gpgsign", "false")
    return repo


class _RaisingStats:
    """Stand-in for a commit whose .stats raises (e.g. shallow boundary)."""

    hexsha = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

    @property
    def stats(self) -> object:
        raise git.GitCommandError(["git", "diff"], 128, b"fatal: bad object")


def test_changed_files_returns_files_for_normal_commit(tmp_path: Path) -> None:
    """A real commit yields its changed C++ files."""
    repo = _init_repo(tmp_path)
    (tmp_path / "a.cpp").write_text("int main() { return 0; }\n")
    repo.index.add(["a.cpp"])
    commit = repo.index.commit("init", author=_DEFAULT, committer=_DEFAULT)

    files = changed_files(commit)
    assert "a.cpp" in files


def test_changed_files_swallows_bad_object_error() -> None:
    """A commit whose stats raise GitCommandError yields an empty mapping."""
    assert changed_files(_RaisingStats()) == {}
