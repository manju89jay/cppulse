"""Git history miner for cppulse.

Extracts per-file metrics from a git repository's commit history,
targeting C++ source files (.cpp, .h, .hpp).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import git

from .commit_utils import changed_files

logger = logging.getLogger(__name__)

CPP_EXTENSIONS: frozenset[str] = frozenset(
    {".cpp", ".h", ".hpp", ".cc", ".cxx", ".hxx"}
)

BUG_KEYWORDS: tuple[str, ...] = ("fix", "bug", "patch", "issue", "crash", "error")


@dataclass
class FileMetrics:
    """Per-file metrics extracted from git history.

    Attributes:
        file: Relative path to the file within the repository.
        change_frequency: Number of commits that touched this file.
        unique_contributors: Count of distinct commit authors.
        age_days: Days since file first appeared in history.
        last_modified_days: Days since most recent commit touching this file.
        lines_of_code: Current line count of the file on disk.
        lines_added_total: Cumulative lines added across all commits.
        lines_removed_total: Cumulative lines removed across all commits.
        churn_rate: (lines_added_total + lines_removed_total) / lines_of_code.
        bug_fix_commits: Commits whose message matches bug-related keywords.
        contributor_list: Ordered list of unique contributor names.
    """

    file: str
    change_frequency: int = 0
    unique_contributors: int = 0
    age_days: int = 0
    last_modified_days: int = 0
    lines_of_code: int = 0
    lines_added_total: int = 0
    lines_removed_total: int = 0
    churn_rate: float = 0.0
    bug_fix_commits: int = 0
    contributor_list: list[str] = field(default_factory=list)


class GitMiner:
    """Extracts per-file metrics from a git repository.

    Only .cpp, .h, .hpp, .cc, .cxx, .hxx files are analyzed.

    Args:
        repo_path: Path to the root of the git repository.
    """

    def __init__(self, repo_path: Path) -> None:
        """Initialize GitMiner with a repository path.

        Args:
            repo_path: Absolute or relative path to the git repository root.

        Raises:
            git.InvalidGitRepositoryError: If repo_path is not a valid git repo.
        """
        self._repo_path = Path(repo_path).resolve()
        self._repo = git.Repo(str(self._repo_path))
        self._now = datetime.now(tz=timezone.utc)

    @property
    def repo(self) -> git.Repo:
        """Return the underlying git.Repo object."""
        return self._repo

    def mine(self) -> list[FileMetrics]:
        """Mine all C++ files in the repository and return their metrics.

        Returns:
            List of FileMetrics, one entry per tracked C++ file.
            Returns an empty list if the repository has no commits.
        """
        try:
            all_commits = list(self._repo.iter_commits())
        except (ValueError, git.GitCommandError):
            logger.warning("Repository has no commits: %s", self._repo_path)
            return []

        if not all_commits:
            logger.warning("Repository has no commits: %s", self._repo_path)
            return []

        file_data: dict[str, dict] = {}

        for commit in all_commits:
            commit_dt = datetime.fromtimestamp(commit.committed_date, tz=timezone.utc)
            is_bug_fix = self._is_bug_fix_commit(commit.message)
            author = commit.author.name or commit.author.email or "unknown"

            stats = changed_files(commit)
            for filepath, file_stat in stats.items():
                if not self._is_cpp_file(filepath):
                    continue

                if filepath not in file_data:
                    file_data[filepath] = {
                        "commit_dates": [],
                        "authors": set(),
                        "lines_added": 0,
                        "lines_removed": 0,
                        "bug_fix_count": 0,
                    }

                entry = file_data[filepath]
                entry["commit_dates"].append(commit_dt)
                entry["authors"].add(author)
                entry["lines_added"] += file_stat.get("insertions", 0)
                entry["lines_removed"] += file_stat.get("deletions", 0)
                if is_bug_fix:
                    entry["bug_fix_count"] += 1

        metrics: list[FileMetrics] = []
        for filepath, data in file_data.items():
            metrics.append(self._build_metrics(filepath, data))

        return metrics

    def _build_metrics(self, filepath: str, data: dict) -> FileMetrics:
        """Build a FileMetrics object from aggregated commit data.

        Args:
            filepath: Relative path of the file within the repository.
            data: Aggregated commit data dict with keys: commit_dates, authors,
                  lines_added, lines_removed, bug_fix_count.

        Returns:
            Populated FileMetrics instance.
        """
        commit_dates: list[datetime] = sorted(data["commit_dates"], reverse=True)
        authors: set[str] = data["authors"]

        change_frequency = len(commit_dates)
        unique_contributors = len(authors)
        contributor_list = sorted(authors)

        oldest = min(commit_dates)
        newest = commit_dates[0]

        age_days = max(0, (self._now - oldest).days)
        last_modified_days = max(0, (self._now - newest).days)

        abs_path = self._repo_path / filepath
        lines_of_code = self._count_lines(abs_path)

        lines_added = data["lines_added"]
        lines_removed = data["lines_removed"]
        churn_rate = (
            (lines_added + lines_removed) / lines_of_code if lines_of_code > 0 else 0.0
        )

        return FileMetrics(
            file=filepath,
            change_frequency=change_frequency,
            unique_contributors=unique_contributors,
            age_days=age_days,
            last_modified_days=last_modified_days,
            lines_of_code=lines_of_code,
            lines_added_total=lines_added,
            lines_removed_total=lines_removed,
            churn_rate=round(churn_rate, 4),
            bug_fix_commits=data["bug_fix_count"],
            contributor_list=contributor_list,
        )

    def commit_range(self) -> str:
        """Return a human-readable commit range string.

        Returns:
            A string of the form ``<first_sha>..<last_sha>``, or the single SHA
            when the repository has exactly one commit, or ``"N/A"`` for empty repos.
        """
        try:
            commits = list(self._repo.iter_commits())
        except (ValueError, git.GitCommandError):
            return "N/A"

        if not commits:
            return "N/A"
        if len(commits) == 1:
            return commits[0].hexsha[:8]
        return f"{commits[-1].hexsha[:8]}..{commits[0].hexsha[:8]}"

    def total_commits(self) -> int:
        """Return the total number of commits reachable from HEAD.

        Returns:
            Integer count of commits, or 0 for empty repositories.
        """
        try:
            return sum(1 for _ in self._repo.iter_commits())
        except (ValueError, git.GitCommandError):
            return 0

    @staticmethod
    def _is_cpp_file(filepath: str) -> bool:
        """Return True if the file has a C++ extension.

        Args:
            filepath: File path string to check.

        Returns:
            True if the extension is in CPP_EXTENSIONS.
        """
        return Path(filepath).suffix.lower() in CPP_EXTENSIONS

    @staticmethod
    def _is_bug_fix_commit(message: str) -> bool:
        """Return True if the commit message contains a bug-related keyword.

        Args:
            message: Commit message text.

        Returns:
            True if any BUG_KEYWORDS appear (case-insensitive).
        """
        lower = message.lower()
        return any(keyword in lower for keyword in BUG_KEYWORDS)

    @staticmethod
    def _count_lines(path: Path) -> int:
        """Count the number of lines in a file.

        Args:
            path: Absolute path to the file.

        Returns:
            Line count, or 0 if the file does not exist or cannot be read.
        """
        try:
            return sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))
        except OSError:
            return 0
