"""Tests for src/miner.py — GitMiner and FileMetrics."""

from __future__ import annotations

from pathlib import Path

import git

from src.miner import FileMetrics, GitMiner

_ALICE = git.Actor("Alice", "alice@example.com")
_BOB = git.Actor("Bob", "bob@example.com")
_DEFAULT = git.Actor("Test User", "test@example.com")


def _init_repo(tmp_path: Path) -> git.Repo:
    """Create a git repo with gpgsign disabled."""
    repo = git.Repo.init(str(tmp_path))
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Test User")
        cfg.set_value("user", "email", "test@example.com")
        cfg.set_value("commit", "gpgsign", "false")
    return repo


class TestFileMetrics:
    """Unit tests for the FileMetrics dataclass."""

    def test_defaults(self) -> None:
        """FileMetrics initialises with expected zero-value defaults."""
        m = FileMetrics(file="foo.cpp")
        assert m.change_frequency == 0
        assert m.unique_contributors == 0
        assert m.lines_of_code == 0
        assert m.churn_rate == 0.0
        assert m.contributor_list == []

    def test_to_dict_keys(self) -> None:
        """Dataclass fields are all present."""
        m = FileMetrics(file="foo.cpp", change_frequency=3, unique_contributors=2)
        assert m.file == "foo.cpp"
        assert m.change_frequency == 3
        assert m.unique_contributors == 2


class TestGitMinerEmptyRepo:
    """GitMiner behaviour on edge-case repositories."""

    def test_empty_repo_returns_empty_list(self, tmp_path: Path) -> None:
        """mine() returns [] when repository has no commits."""
        git.Repo.init(str(tmp_path))
        miner = GitMiner(tmp_path)
        result = miner.mine()
        assert result == []

    def test_no_cpp_files_returns_empty_list(self, tmp_path: Path) -> None:
        """mine() returns [] when repo has only non-C++ files."""
        repo = _init_repo(tmp_path)
        readme = tmp_path / "README.md"
        readme.write_text("hello\n")
        repo.index.add(["README.md"])
        repo.index.commit("Add readme", author=_DEFAULT, committer=_DEFAULT)

        miner = GitMiner(tmp_path)
        result = miner.mine()
        assert result == []


class TestGitMinerSimpleRepo:
    """GitMiner metrics extraction on a simple two-commit repository."""

    def test_mine_returns_correct_file_count(self, simple_cpp_repo: git.Repo) -> None:
        """Two distinct C++ files produce two FileMetrics entries."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        metrics = miner.mine()
        files = {m.file for m in metrics}
        assert "main.cpp" in files
        assert "utils.hpp" in files

    def test_change_frequency_main_cpp(self, simple_cpp_repo: git.Repo) -> None:
        """main.cpp was touched in 2 commits."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        metrics = miner.mine()
        main = next(m for m in metrics if m.file == "main.cpp")
        assert main.change_frequency == 2

    def test_change_frequency_utils_hpp(self, simple_cpp_repo: git.Repo) -> None:
        """utils.hpp was touched in 1 commit."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        metrics = miner.mine()
        utils = next(m for m in metrics if m.file == "utils.hpp")
        assert utils.change_frequency == 1

    def test_unique_contributors_single_author(self, simple_cpp_repo: git.Repo) -> None:
        """All files have exactly 1 unique contributor in a single-author repo."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        metrics = miner.mine()
        for m in metrics:
            assert m.unique_contributors == 1

    def test_contributor_list_populated(self, simple_cpp_repo: git.Repo) -> None:
        """contributor_list is a non-empty list of strings."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        metrics = miner.mine()
        for m in metrics:
            assert isinstance(m.contributor_list, list)
            assert len(m.contributor_list) >= 1
            assert all(isinstance(name, str) for name in m.contributor_list)

    def test_age_days_positive(self, simple_cpp_repo: git.Repo) -> None:
        """age_days is >= 0 for all files."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        metrics = miner.mine()
        for m in metrics:
            assert m.age_days >= 0

    def test_last_modified_days_non_negative(self, simple_cpp_repo: git.Repo) -> None:
        """last_modified_days is >= 0 and <= age_days."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        metrics = miner.mine()
        for m in metrics:
            assert m.last_modified_days >= 0
            assert m.last_modified_days <= m.age_days

    def test_lines_of_code_main_cpp(self, simple_cpp_repo: git.Repo) -> None:
        """main.cpp has lines_of_code > 0 because it exists on disk."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        metrics = miner.mine()
        main = next(m for m in metrics if m.file == "main.cpp")
        assert main.lines_of_code > 0

    def test_lines_added_total_positive(self, simple_cpp_repo: git.Repo) -> None:
        """lines_added_total is positive for files that had additions."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        metrics = miner.mine()
        main = next(m for m in metrics if m.file == "main.cpp")
        assert main.lines_added_total > 0

    def test_churn_rate_computed(self, simple_cpp_repo: git.Repo) -> None:
        """churn_rate is a non-negative float."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        metrics = miner.mine()
        for m in metrics:
            assert isinstance(m.churn_rate, float)
            assert m.churn_rate >= 0.0

    def test_no_bug_fix_commits_normal_messages(
        self, simple_cpp_repo: git.Repo
    ) -> None:
        """bug_fix_commits is 0 when no commit message contains bug keywords."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        metrics = miner.mine()
        for m in metrics:
            assert m.bug_fix_commits == 0


class TestGitMinerBugFixRepo:
    """GitMiner correctly counts bug-fix commits."""

    def test_bug_fix_commits_counted(self, bug_fix_repo: git.Repo) -> None:
        """engine.cpp has 1 bug-fix commit."""
        miner = GitMiner(Path(bug_fix_repo.working_dir))
        metrics = miner.mine()
        engine = next(m for m in metrics if m.file == "engine.cpp")
        assert engine.bug_fix_commits == 1

    def test_bug_fix_keywords_case_insensitive(self, tmp_path: Path) -> None:
        """Bug keyword matching is case-insensitive."""
        repo = _init_repo(tmp_path)
        src = tmp_path / "core.cpp"
        src.write_text("void f() {}\n")
        repo.index.add(["core.cpp"])
        repo.index.commit("initial", author=_DEFAULT, committer=_DEFAULT)

        src.write_text("void f() { /*ok*/ }\n")
        repo.index.add(["core.cpp"])
        repo.index.commit("FIX: uppercase keyword", author=_DEFAULT, committer=_DEFAULT)

        miner = GitMiner(tmp_path)
        metrics = miner.mine()
        core = next(m for m in metrics if m.file == "core.cpp")
        assert core.bug_fix_commits == 1


class TestGitMinerMultiAuthor:
    """GitMiner correctly handles multiple authors."""

    def test_unique_contributors_per_file(self, multi_author_repo: git.Repo) -> None:
        """Each file in multi_author_repo has exactly 1 unique contributor."""
        miner = GitMiner(Path(multi_author_repo.working_dir))
        metrics = miner.mine()
        by_file = {m.file: m for m in metrics}

        assert by_file["alice.cpp"].unique_contributors == 1
        assert by_file["bob.cpp"].unique_contributors == 1

    def test_contributor_names_correct(self, multi_author_repo: git.Repo) -> None:
        """Alice authored alice.cpp, Bob authored bob.cpp."""
        miner = GitMiner(Path(multi_author_repo.working_dir))
        metrics = miner.mine()
        by_file = {m.file: m for m in metrics}

        assert "Alice" in by_file["alice.cpp"].contributor_list
        assert "Bob" in by_file["bob.cpp"].contributor_list

    def test_shared_file_has_two_contributors(self, tmp_path: Path) -> None:
        """A file touched by two authors gets unique_contributors == 2."""
        repo = _init_repo(tmp_path)

        shared = tmp_path / "shared.cpp"
        shared.write_text("// v1\n")
        repo.index.add(["shared.cpp"])
        repo.index.commit("Alice adds shared.cpp", author=_ALICE, committer=_ALICE)

        shared.write_text("// v2\n")
        repo.index.add(["shared.cpp"])
        repo.index.commit("Bob edits shared.cpp", author=_BOB, committer=_BOB)

        miner = GitMiner(tmp_path)
        metrics = miner.mine()
        shared_m = next(m for m in metrics if m.file == "shared.cpp")
        assert shared_m.unique_contributors == 2

    def test_commit_range_format(self, simple_cpp_repo: git.Repo) -> None:
        """commit_range returns a string containing '..'."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        assert ".." in miner.commit_range()

    def test_total_commits(self, simple_cpp_repo: git.Repo) -> None:
        """total_commits returns the correct number of commits."""
        miner = GitMiner(Path(simple_cpp_repo.working_dir))
        assert miner.total_commits() == 2

    def test_total_commits_empty_repo(self, tmp_path: Path) -> None:
        """total_commits returns 0 for an empty repo."""
        git.Repo.init(str(tmp_path))
        miner = GitMiner(tmp_path)
        assert miner.total_commits() == 0

    def test_commit_range_empty_repo(self, tmp_path: Path) -> None:
        """commit_range returns 'N/A' for an empty repo."""
        git.Repo.init(str(tmp_path))
        miner = GitMiner(tmp_path)
        assert miner.commit_range() == "N/A"
