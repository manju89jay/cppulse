"""Actual Git inventory scope, repository helper suppression and finite failures."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import git
import pytest

from cppulse.errors import IntegrityError
from cppulse.git_miner.history import current_cpp_files


def fixture_repo(path: Path) -> git.Repo:
    repo = git.Repo.init(path)
    root = Path(repo.working_tree_dir)
    (root / "a.cpp").write_text("int a=1;\n")
    repo.index.add(["a.cpp"])
    actor = git.Actor("Fixture", "fixture@example.invalid")
    repo.index.commit("initial", author=actor, committer=actor)
    return repo


def test_repository_fsmonitor_is_never_executed_by_inventory(tmp_path):
    repo = fixture_repo(tmp_path / "repo")
    marker = tmp_path / "hook-ran"
    hook = tmp_path / "hook"
    hook.write_text('#!/bin/sh\nprintf ran > "' + str(marker) + '"\nexit 0\n')
    hook.chmod(0o700)
    with repo.config_writer() as writer:
        writer.set_value("core", "fsmonitor", str(hook))
    assert current_cpp_files(repo) == {"a.cpp"}
    assert not marker.exists()


def test_inherited_other_repository_and_index_do_not_expand_scope(
    tmp_path, monkeypatch
):
    repo = fixture_repo(tmp_path / "selected")
    other = fixture_repo(tmp_path / "other")
    (Path(repo.working_tree_dir) / "b.cpp").write_text("int b=2;\n")
    (Path(other.working_tree_dir) / "b.cpp").write_text("int b=2;\n")
    other.index.add(["b.cpp"])
    monkeypatch.setenv("GIT_DIR", other.git_dir)
    monkeypatch.setenv("GIT_WORK_TREE", other.working_tree_dir)
    monkeypatch.setenv("GIT_INDEX_FILE", str(Path(other.git_dir) / "index"))
    monkeypatch.setenv("GIT_NAMESPACE", "foreign")
    assert current_cpp_files(repo) == {"a.cpp"}


def test_inventory_timeout_is_operational_failure(tmp_path, monkeypatch):
    import cppulse.git_miner.history as history

    repo = fixture_repo(tmp_path / "repo")
    # A real fast Git may exit before the supervisor first polls. An owned slow
    # selected executable deterministically exercises actual timeout/termination.
    slow_git = tmp_path / "slow-git"
    slow_git.write_text("#!/bin/sh\nexec /usr/bin/sleep 30\n")
    slow_git.chmod(0o700)
    original_which = history.shutil.which
    monkeypatch.setattr(
        history.shutil,
        "which",
        lambda name: str(slow_git) if name == "git" else original_which(name),
    )
    with pytest.raises(IntegrityError, match="inventory"):
        current_cpp_files(repo, timeout_seconds=0.2)


def test_inventory_capture_limit_is_failure_not_truncated_scope(tmp_path, monkeypatch):
    import cppulse.git_miner.history as history

    repo = fixture_repo(tmp_path / "repo")
    monkeypatch.setattr(history, "MAX_INVENTORY_BYTES", 1)
    with pytest.raises(IntegrityError, match="inventory"):
        current_cpp_files(repo)


def test_inventory_entry_limit_includes_non_cpp_paths(tmp_path, monkeypatch):
    import cppulse.git_miner.history as history

    repo = fixture_repo(tmp_path / "repo")
    (Path(repo.working_tree_dir) / "README").write_text("tracked\n")
    repo.index.add(["README"])
    monkeypatch.setattr(history, "MAX_TRACKED_PATHS", 1)
    with pytest.raises(IntegrityError, match="entry"):
        current_cpp_files(repo)


def test_inventory_path_byte_limit_is_finite(tmp_path, monkeypatch):
    import cppulse.git_miner.history as history

    repo = fixture_repo(tmp_path / "repo")
    monkeypatch.setattr(history, "MAX_TRACKED_PATH_BYTES", 2)
    with pytest.raises(IntegrityError, match="path"):
        current_cpp_files(repo)


def test_unrepresentable_utf8_path_is_not_silently_missing(tmp_path):
    repo = fixture_repo(tmp_path / "repo")
    filename = os.fsencode(repo.working_tree_dir) + b"/invalid-\xff.cpp"
    descriptor = os.open(filename, os.O_CREAT | os.O_WRONLY, 0o600)
    os.write(descriptor, b"int a=1;\n")
    os.close(descriptor)
    subprocess.run(
        [
            b"/usr/bin/git",
            b"-C",
            os.fsencode(repo.working_tree_dir),
            b"add",
            b"--",
            b"invalid-\xff.cpp",
        ],
        check=True,
    )
    with pytest.raises(IntegrityError, match="UTF-8"):
        current_cpp_files(repo)


def test_unicode_control_and_renamed_tracked_paths_are_exact(tmp_path):
    repo = fixture_repo(tmp_path / "repo")
    root = Path(repo.working_tree_dir)
    names = {"unicodé.cpp", "tab\tname.hpp", "line\nname.cc"}
    for name in names:
        (root / name).write_text("int a=1;\n")
    repo.index.add(sorted(names))
    assert current_cpp_files(repo) == {"a.cpp", *names}


def test_symlink_and_worktree_deleted_inventory_preserve_limitations(tmp_path):
    repo = fixture_repo(tmp_path / "repo")
    root = Path(repo.working_tree_dir)
    (root / "a.cpp").unlink()
    (root / "linked.cpp").symlink_to(tmp_path / "outside.cpp")
    repo.index.add(["linked.cpp"])
    notes = []
    assert current_cpp_files(repo, notes) == set()
    assert "Skipped tracked symlink path: linked.cpp." in notes


def test_inherited_trace_does_not_write_an_extra_file(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path / "repo")
    trace = tmp_path / "unrequested-trace"
    monkeypatch.setenv("GIT_TRACE", str(trace))
    assert current_cpp_files(repo) == {"a.cpp"}
    assert not trace.exists()


def test_inherited_reference_trace_does_not_escape_full_scan(tmp_path, monkeypatch):
    from cppulse.git_miner.history import scan_history

    repo = fixture_repo(tmp_path / "repo")
    trace = tmp_path / "unrequested-ref-trace"
    monkeypatch.setenv("GIT_TRACE_REFS", str(trace))
    scan = scan_history(repo, options={"cache_dir": str(tmp_path / "cache")})
    try:
        assert list(scan.changes)
        assert not trace.exists()
    finally:
        scan._cache_owner.close()
