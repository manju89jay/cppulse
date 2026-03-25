"""Tests for src/szz_labeler.py — SZZLabeler."""

from __future__ import annotations

from pathlib import Path

import git

from src.szz_labeler import SZZLabeler

_DEFAULT = git.Actor("Dev", "dev@example.com")


def _init_repo(tmp_path: Path) -> git.Repo:
    """Create a git repo with gpgsign disabled."""
    repo = git.Repo.init(str(tmp_path))
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Dev")
        cfg.set_value("user", "email", "dev@example.com")
        cfg.set_value("commit", "gpgsign", "false")
    return repo


class TestSZZLabelerEdgeCases:
    """SZZLabeler behaviour on empty and non-C++ repositories."""

    def test_empty_repo_returns_empty_dict(self, tmp_path: Path) -> None:
        """label() returns {} for a repo with no commits."""
        git.Repo.init(str(tmp_path))
        labeler = SZZLabeler(tmp_path)
        assert labeler.label() == {}

    def test_no_bug_fix_commits_returns_empty(self, tmp_path: Path) -> None:
        """label() returns {} when no commit message contains bug keywords."""
        repo = _init_repo(tmp_path)
        src = tmp_path / "main.cpp"
        src.write_text("int main() { return 0; }\n")
        repo.index.add(["main.cpp"])
        repo.index.commit("Initial implementation", author=_DEFAULT, committer=_DEFAULT)

        src.write_text("int main() { return 1; }\n")
        repo.index.add(["main.cpp"])
        repo.index.commit("Update return value", author=_DEFAULT, committer=_DEFAULT)

        labeler = SZZLabeler(tmp_path)
        result = labeler.label()
        assert result == {}

    def test_no_cpp_files_returns_empty(self, tmp_path: Path) -> None:
        """label() returns {} when there are no C++ files in the bug-fix commit."""
        repo = _init_repo(tmp_path)
        readme = tmp_path / "README.md"
        readme.write_text("hello\n")
        repo.index.add(["README.md"])
        repo.index.commit("Add readme", author=_DEFAULT, committer=_DEFAULT)

        readme.write_text("hello world\n")
        repo.index.add(["README.md"])
        repo.index.commit("fix: typo in readme", author=_DEFAULT, committer=_DEFAULT)

        labeler = SZZLabeler(tmp_path)
        result = labeler.label()
        assert result == {}


class TestSZZLabelerBugFixDetection:
    """SZZLabeler correctly identifies bug-introducing commits."""

    def test_bug_fix_commit_labels_introducing_file(
        self, bug_fix_repo: git.Repo
    ) -> None:
        """engine.cpp is identified as having bug-introducing commits."""
        labeler = SZZLabeler(Path(bug_fix_repo.working_dir))
        result = labeler.label()
        assert "engine.cpp" in result

    def test_bug_introducing_count_positive(self, bug_fix_repo: git.Repo) -> None:
        """The count of bug-introducing commits for engine.cpp is >= 1."""
        labeler = SZZLabeler(Path(bug_fix_repo.working_dir))
        result = labeler.label()
        assert result["engine.cpp"] >= 1

    def test_result_is_dict_of_int(self, bug_fix_repo: git.Repo) -> None:
        """Return type is dict[str, int] with positive integer values."""
        labeler = SZZLabeler(Path(bug_fix_repo.working_dir))
        result = labeler.label()
        for file_path, count in result.items():
            assert isinstance(file_path, str)
            assert isinstance(count, int)
            assert count >= 1

    def test_multiple_bug_fix_commits(self, tmp_path: Path) -> None:
        """Multiple bug-fix commits accumulate correctly."""
        repo = _init_repo(tmp_path)

        src = tmp_path / "core.cpp"
        src.write_text("void f() {}\n")
        repo.index.add(["core.cpp"])
        repo.index.commit("Initial commit", author=_DEFAULT, committer=_DEFAULT)

        src.write_text("void f() { /* v2 */ }\n")
        repo.index.add(["core.cpp"])
        repo.index.commit("fix: first bug", author=_DEFAULT, committer=_DEFAULT)

        src.write_text("void f() { /* v3 */ }\n")
        repo.index.add(["core.cpp"])
        repo.index.commit("patch: second issue", author=_DEFAULT, committer=_DEFAULT)

        labeler = SZZLabeler(tmp_path)
        result = labeler.label()
        assert "core.cpp" in result
        assert result["core.cpp"] >= 1

    def test_keyword_case_insensitive(self, tmp_path: Path) -> None:
        """Bug keywords are matched case-insensitively."""
        repo = _init_repo(tmp_path)

        src = tmp_path / "lib.cpp"
        src.write_text("int x = 1;\n")
        repo.index.add(["lib.cpp"])
        repo.index.commit("initial", author=_DEFAULT, committer=_DEFAULT)

        src.write_text("int x = 2;\n")
        repo.index.add(["lib.cpp"])
        repo.index.commit("BUG: uppercase keyword", author=_DEFAULT, committer=_DEFAULT)

        labeler = SZZLabeler(tmp_path)
        result = labeler.label()
        assert "lib.cpp" in result


class TestSZZLabelerFirstCommit:
    """SZZLabeler handles the edge case where the bug-fix IS the first commit."""

    def test_single_commit_bug_fix_returns_empty(self, tmp_path: Path) -> None:
        """If the only commit is a bug-fix with no parent, nothing is blamed."""
        repo = _init_repo(tmp_path)

        src = tmp_path / "main.cpp"
        src.write_text("int main() {}\n")
        repo.index.add(["main.cpp"])
        repo.index.commit(
            "fix: initial fix with no parent",
            author=_DEFAULT,
            committer=_DEFAULT,
        )

        labeler = SZZLabeler(tmp_path)
        result = labeler.label()
        # No parent means no blame possible; result should be empty
        assert result == {}
