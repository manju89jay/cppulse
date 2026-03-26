"""Shared pytest fixtures for git-miner tests.

Provides helper utilities to create temporary git repositories
with controlled commit histories for deterministic testing.
"""

from __future__ import annotations

from pathlib import Path

import git
import pytest

_ALICE = git.Actor("Alice", "alice@example.com")
_BOB = git.Actor("Bob", "bob@example.com")
_DEFAULT_ACTOR = git.Actor("Test User", "test@example.com")


def _configure_repo(
    repo: git.Repo, name: str = "Test User", email: str = "test@example.com"
) -> None:
    """Set author/committer config on a repo so commits do not fail.

    Args:
        repo: The git.Repo to configure.
        name: Author name string.
        email: Author email string.
    """
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", name)
        cfg.set_value("user", "email", email)
        cfg.set_value("commit", "gpgsign", "false")


@pytest.fixture()
def simple_cpp_repo(tmp_path: Path) -> git.Repo:
    """Fixture: a git repo with two C++ commits by one author.

    Layout after fixture:
        main.cpp  — created in commit 1, modified in commit 2
        utils.hpp — created in commit 1

    Returns:
        Initialized git.Repo at tmp_path.
    """
    repo = git.Repo.init(str(tmp_path))
    _configure_repo(repo)

    # Commit 1
    cpp_file = tmp_path / "main.cpp"
    hpp_file = tmp_path / "utils.hpp"
    cpp_file.write_text("int main() { return 0; }\n")
    hpp_file.write_text("void util();\n")
    repo.index.add(["main.cpp", "utils.hpp"])
    repo.index.commit(
        "Initial commit",
        author=_DEFAULT_ACTOR,
        committer=_DEFAULT_ACTOR,
    )

    # Commit 2
    cpp_file.write_text("int main() { return 0; }\n// added\n")
    repo.index.add(["main.cpp"])
    repo.index.commit(
        "Update main.cpp",
        author=_DEFAULT_ACTOR,
        committer=_DEFAULT_ACTOR,
    )

    return repo


@pytest.fixture()
def multi_author_repo(tmp_path: Path) -> git.Repo:
    """Fixture: a repo where two different authors each commit to separate files.

    Alice commits only to alice.cpp.
    Bob commits only to bob.cpp.

    Returns:
        Initialized git.Repo at tmp_path.
    """
    repo = git.Repo.init(str(tmp_path))
    _configure_repo(repo, name="Alice", email="alice@example.com")

    alice_file = tmp_path / "alice.cpp"
    alice_file.write_text("// alice\n")
    repo.index.add(["alice.cpp"])
    repo.index.commit(
        "Alice commit",
        author=_ALICE,
        committer=_ALICE,
    )

    bob_file = tmp_path / "bob.cpp"
    bob_file.write_text("// bob\n")
    repo.index.add(["bob.cpp"])
    repo.index.commit(
        "Bob commit",
        author=_BOB,
        committer=_BOB,
    )

    return repo


@pytest.fixture()
def bug_fix_repo(tmp_path: Path) -> git.Repo:
    """Fixture: repo with a normal commit followed by a bug-fix commit.

    Returns:
        Initialized git.Repo at tmp_path.
    """
    repo = git.Repo.init(str(tmp_path))
    _configure_repo(repo)

    src = tmp_path / "engine.cpp"
    src.write_text("void engine() {}\n")
    repo.index.add(["engine.cpp"])
    repo.index.commit(
        "Initial implementation",
        author=_DEFAULT_ACTOR,
        committer=_DEFAULT_ACTOR,
    )

    src.write_text("void engine() { /* fixed */ }\n")
    repo.index.add(["engine.cpp"])
    repo.index.commit(
        "fix: resolve crash in engine",
        author=_DEFAULT_ACTOR,
        committer=_DEFAULT_ACTOR,
    )

    return repo
