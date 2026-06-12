"""Tests for src/main.py — CLI entry point and build_output helper."""

from __future__ import annotations

import json
from pathlib import Path

import git
import pytest

from src.main import build_output, parse_args, run
from src.miner import FileMetrics
from src.silo_detector import SiloEntry

_DEFAULT = git.Actor("Dev", "dev@example.com")


def _init_repo(tmp_path: Path) -> git.Repo:
    """Create a git repo with gpgsign disabled."""
    repo = git.Repo.init(str(tmp_path))
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Dev")
        cfg.set_value("user", "email", "dev@example.com")
        cfg.set_value("commit", "gpgsign", "false")
    return repo


class TestParseArgs:
    """Tests for the parse_args() function."""

    def test_required_repo_argument(self, tmp_path: Path) -> None:
        """parse_args parses --repo correctly."""
        args = parse_args(["--repo", str(tmp_path)])
        assert args.repo == tmp_path

    def test_default_output_directory(self, tmp_path: Path) -> None:
        """Default output directory is ./output."""
        args = parse_args(["--repo", str(tmp_path)])
        assert str(args.output) == "output"

    def test_custom_output_directory(self, tmp_path: Path) -> None:
        """Custom --output argument is parsed correctly."""
        out = tmp_path / "my_output"
        args = parse_args(["--repo", str(tmp_path), "--output", str(out)])
        assert args.output == out

    def test_missing_repo_raises(self) -> None:
        """SystemExit is raised when --repo is omitted."""
        with pytest.raises(SystemExit):
            parse_args([])


class TestBuildOutput:
    """Tests for the build_output() helper function."""

    def test_version_field(self, tmp_path: Path) -> None:
        """Output document always has version '1.0.0'."""
        repo = _init_repo(tmp_path)
        src = tmp_path / "a.cpp"
        src.write_text("// a\n")
        repo.index.add(["a.cpp"])
        repo.index.commit("init", author=_DEFAULT, committer=_DEFAULT)

        result = build_output(tmp_path, [], [], repo)
        assert result["version"] == "1.0.0"

    def test_metadata_keys_present(self, tmp_path: Path) -> None:
        """Metadata block contains all required keys."""
        repo = _init_repo(tmp_path)
        src = tmp_path / "a.cpp"
        src.write_text("// a\n")
        repo.index.add(["a.cpp"])
        repo.index.commit("init", author=_DEFAULT, committer=_DEFAULT)

        result = build_output(tmp_path, [], [], repo)
        meta = result["metadata"]
        assert "repo_path" in meta
        assert "analyzed_at" in meta
        assert "commit_range" in meta
        assert "total_commits" in meta

    def test_total_commits_count(self, tmp_path: Path) -> None:
        """total_commits reflects actual commit count in the repo."""
        repo = _init_repo(tmp_path)
        src = tmp_path / "a.cpp"
        src.write_text("// v1\n")
        repo.index.add(["a.cpp"])
        repo.index.commit("commit 1", author=_DEFAULT, committer=_DEFAULT)

        src.write_text("// v2\n")
        repo.index.add(["a.cpp"])
        repo.index.commit("commit 2", author=_DEFAULT, committer=_DEFAULT)

        result = build_output(tmp_path, [], [], repo)
        assert result["metadata"]["total_commits"] == 2

    def test_file_metrics_serialized(self, tmp_path: Path) -> None:
        """file_metrics list is serialized correctly from FileMetrics objects."""
        repo = _init_repo(tmp_path)
        src = tmp_path / "a.cpp"
        src.write_text("// a\n")
        repo.index.add(["a.cpp"])
        repo.index.commit("init", author=_DEFAULT, committer=_DEFAULT)

        metrics = [
            FileMetrics(
                file="main.cpp",
                change_frequency=3,
                unique_contributors=1,
                age_days=10,
                last_modified_days=2,
                lines_of_code=50,
                lines_added_total=60,
                lines_removed_total=10,
                churn_rate=1.4,
                bug_fix_commits=1,
                contributor_list=["Alice"],
            )
        ]
        result = build_output(tmp_path, metrics, [], repo)
        assert len(result["file_metrics"]) == 1
        fm = result["file_metrics"][0]
        assert fm["file"] == "main.cpp"
        assert fm["change_frequency"] == 3
        assert fm["contributor_list"] == ["Alice"]

    def test_knowledge_silos_serialized(self, tmp_path: Path) -> None:
        """knowledge_silos list is serialized correctly from SiloEntry objects."""
        repo = _init_repo(tmp_path)
        src = tmp_path / "a.cpp"
        src.write_text("// a\n")
        repo.index.add(["a.cpp"])
        repo.index.commit("init", author=_DEFAULT, committer=_DEFAULT)

        silos = [
            SiloEntry(
                file="old.cpp",
                sole_contributor="Bob",
                last_commit_date="2024-06-01",
                risk_note="Bus factor: 1.",
            )
        ]
        result = build_output(tmp_path, [], silos, repo)
        assert len(result["knowledge_silos"]) == 1
        silo = result["knowledge_silos"][0]
        assert silo["file"] == "old.cpp"
        assert silo["sole_contributor"] == "Bob"

    def test_empty_repo_commit_range(self, tmp_path: Path) -> None:
        """build_output handles repos where iter_commits returns nothing."""
        repo = git.Repo.init(str(tmp_path))
        result = build_output(tmp_path, [], [], repo)
        assert result["metadata"]["commit_range"] in ("empty", "unknown")
        assert result["metadata"]["total_commits"] == 0


class TestRunFunction:
    """Tests for the run() entry point."""

    def test_run_nonexistent_path_returns_1(self, tmp_path: Path) -> None:
        """run() returns 1 when the repo path does not exist."""
        bad_path = tmp_path / "does_not_exist"
        result = run(bad_path, tmp_path / "out")
        assert result == 1

    def test_run_non_git_dir_returns_1(self, tmp_path: Path) -> None:
        """run() returns 1 when path exists but is not a git repo."""
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        result = run(plain_dir, tmp_path / "out")
        assert result == 1

    def test_run_valid_repo_creates_output(self, tmp_path: Path) -> None:
        """run() returns 0 and creates git_metrics.json for a valid repo."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _init_repo(repo_dir)
        src = repo_dir / "main.cpp"
        src.write_text("int main() { return 0; }\n")
        repo.index.add(["main.cpp"])
        repo.index.commit("initial", author=_DEFAULT, committer=_DEFAULT)

        out_dir = tmp_path / "output"
        result = run(repo_dir, out_dir)
        assert result == 0
        assert (out_dir / "git_metrics.json").exists()

    def test_run_output_is_valid_json(self, tmp_path: Path) -> None:
        """The created git_metrics.json is valid JSON."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _init_repo(repo_dir)
        src = repo_dir / "main.cpp"
        src.write_text("int main() { return 0; }\n")
        repo.index.add(["main.cpp"])
        repo.index.commit("initial", author=_DEFAULT, committer=_DEFAULT)

        out_dir = tmp_path / "output"
        run(repo_dir, out_dir)

        content = (out_dir / "git_metrics.json").read_text()
        data = json.loads(content)
        assert data["version"] == "1.0.0"
        assert "file_metrics" in data

    def test_run_empty_repo_succeeds(self, tmp_path: Path) -> None:
        """run() returns 0 even for an empty git repo (no commits)."""
        repo_dir = tmp_path / "empty_repo"
        repo_dir.mkdir()
        git.Repo.init(str(repo_dir))

        out_dir = tmp_path / "output"
        result = run(repo_dir, out_dir)
        assert result == 0
        assert (out_dir / "git_metrics.json").exists()


class TestBuildOutputSZZ:
    """SZZ counts are merged into serialized file metrics."""

    def test_szz_counts_merged_into_file_metrics(self, tmp_path: Path) -> None:
        """Files present in szz_counts carry their bug-introduction count."""
        repo = _init_repo(tmp_path)
        src = tmp_path / "a.cpp"
        src.write_text("// a\n")
        repo.index.add(["a.cpp"])
        repo.index.commit("init", author=_DEFAULT, committer=_DEFAULT)

        metrics = [FileMetrics(file="a.cpp"), FileMetrics(file="b.cpp")]
        result = build_output(tmp_path, metrics, [], repo, szz_counts={"a.cpp": 2})

        by_file = {m["file"]: m for m in result["file_metrics"]}
        assert by_file["a.cpp"]["szz_bug_introductions"] == 2
        assert by_file["b.cpp"]["szz_bug_introductions"] == 0

    def test_szz_field_defaults_to_zero_without_counts(self, tmp_path: Path) -> None:
        """Omitting szz_counts still emits the field with value 0."""
        repo = _init_repo(tmp_path)
        src = tmp_path / "a.cpp"
        src.write_text("// a\n")
        repo.index.add(["a.cpp"])
        repo.index.commit("init", author=_DEFAULT, committer=_DEFAULT)

        result = build_output(tmp_path, [FileMetrics(file="a.cpp")], [], repo)
        assert result["file_metrics"][0]["szz_bug_introductions"] == 0


class TestRunWritesSZZ:
    """End-to-end: run() produces git_metrics.json with SZZ data."""

    def test_run_emits_szz_field_for_bug_fix_history(self, tmp_path: Path) -> None:
        """A repo with a fix commit yields a non-zero SZZ count for the file."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _init_repo(repo_dir)
        src = repo_dir / "main.cpp"
        src.write_text("int main() { return 0; }\n")
        repo.index.add(["main.cpp"])
        repo.index.commit("Initial implementation", author=_DEFAULT, committer=_DEFAULT)

        src.write_text("int main() { return 1; }\n")
        repo.index.add(["main.cpp"])
        repo.index.commit(
            "fix: wrong return value", author=_DEFAULT, committer=_DEFAULT
        )

        out_dir = tmp_path / "out"
        assert run(repo_dir, out_dir) == 0

        data = json.loads((out_dir / "git_metrics.json").read_text())
        by_file = {m["file"]: m for m in data["file_metrics"]}
        assert by_file["main.cpp"]["szz_bug_introductions"] >= 1
