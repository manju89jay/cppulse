"""Tests for src/silo_detector.py — SiloDetector and SiloEntry."""

from __future__ import annotations

import re
from pathlib import Path

import git

from src.silo_detector import SiloDetector, SiloEntry

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


class TestSiloDetectorEdgeCases:
    """SiloDetector behaviour on edge-case repositories."""

    def test_empty_repo_returns_empty(self, tmp_path: Path) -> None:
        """detect() returns [] for a repo with no commits."""
        git.Repo.init(str(tmp_path))
        detector = SiloDetector(tmp_path)
        assert detector.detect() == []

    def test_no_cpp_files_returns_empty(self, tmp_path: Path) -> None:
        """detect() returns [] when there are no C++ files in history."""
        repo = _init_repo(tmp_path)
        readme = tmp_path / "README.md"
        readme.write_text("hello\n")
        repo.index.add(["README.md"])
        repo.index.commit("Add readme", author=_DEFAULT, committer=_DEFAULT)

        detector = SiloDetector(tmp_path)
        assert detector.detect() == []


class TestSiloDetectorSingleAuthor:
    """SiloDetector correctly identifies single-author files as silos."""

    def test_single_author_file_detected(self, simple_cpp_repo: git.Repo) -> None:
        """All files in the single-author repo are detected as silos."""
        detector = SiloDetector(Path(simple_cpp_repo.working_dir))
        silos = detector.detect()
        silo_files = {s.file for s in silos}
        assert "main.cpp" in silo_files
        assert "utils.hpp" in silo_files

    def test_silo_entry_fields_populated(self, simple_cpp_repo: git.Repo) -> None:
        """SiloEntry has non-empty string fields for sole_contributor and last_commit_date."""
        detector = SiloDetector(Path(simple_cpp_repo.working_dir))
        silos = detector.detect()
        assert len(silos) > 0
        for silo in silos:
            assert isinstance(silo.file, str) and silo.file
            assert isinstance(silo.sole_contributor, str) and silo.sole_contributor
            assert isinstance(silo.last_commit_date, str) and silo.last_commit_date
            assert isinstance(silo.risk_note, str)

    def test_last_commit_date_format(self, simple_cpp_repo: git.Repo) -> None:
        """last_commit_date is in YYYY-MM-DD format."""
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        detector = SiloDetector(Path(simple_cpp_repo.working_dir))
        silos = detector.detect()
        for silo in silos:
            assert date_pattern.match(
                silo.last_commit_date
            ), f"Invalid date format: {silo.last_commit_date}"

    def test_risk_note_mentions_sole_contributor(
        self, simple_cpp_repo: git.Repo
    ) -> None:
        """risk_note contains the sole contributor's name."""
        detector = SiloDetector(Path(simple_cpp_repo.working_dir))
        silos = detector.detect()
        for silo in silos:
            assert silo.sole_contributor in silo.risk_note


class TestSiloDetectorMultiAuthor:
    """SiloDetector does not flag files with multiple contributors."""

    def test_shared_file_not_a_silo(self, tmp_path: Path) -> None:
        """A file committed by two authors is NOT flagged as a silo."""
        repo = _init_repo(tmp_path)

        shared = tmp_path / "shared.cpp"
        shared.write_text("// v1\n")
        repo.index.add(["shared.cpp"])
        repo.index.commit("Alice creates shared.cpp", author=_ALICE, committer=_ALICE)

        shared.write_text("// v2\n")
        repo.index.add(["shared.cpp"])
        repo.index.commit("Bob edits shared.cpp", author=_BOB, committer=_BOB)

        detector = SiloDetector(tmp_path)
        silos = detector.detect()
        silo_files = {s.file for s in silos}
        assert "shared.cpp" not in silo_files

    def test_separate_files_each_sole_author_both_silos(
        self, multi_author_repo: git.Repo
    ) -> None:
        """alice.cpp and bob.cpp are each silos since each has only 1 contributor."""
        detector = SiloDetector(Path(multi_author_repo.working_dir))
        silos = detector.detect()
        silo_files = {s.file for s in silos}
        assert "alice.cpp" in silo_files
        assert "bob.cpp" in silo_files

    def test_silo_sole_contributor_is_correct_author(
        self, multi_author_repo: git.Repo
    ) -> None:
        """The sole_contributor for alice.cpp is Alice."""
        detector = SiloDetector(Path(multi_author_repo.working_dir))
        silos = detector.detect()
        by_file = {s.file: s for s in silos}
        assert by_file["alice.cpp"].sole_contributor == "Alice"
        assert by_file["bob.cpp"].sole_contributor == "Bob"


class TestSiloEntry:
    """Unit tests for the SiloEntry dataclass."""

    def test_silo_entry_construction(self) -> None:
        """SiloEntry can be constructed with required fields."""
        entry = SiloEntry(
            file="foo.cpp",
            sole_contributor="Alice",
            last_commit_date="2025-01-15",
            risk_note="Bus factor: 1.",
        )
        assert entry.file == "foo.cpp"
        assert entry.sole_contributor == "Alice"
        assert entry.last_commit_date == "2025-01-15"
        assert entry.risk_note == "Bus factor: 1."
