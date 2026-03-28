"""Knowledge silo detector for cppulse git-miner.

Identifies files that have been modified by only one contributor in the
last 12 months — a knowledge silo risk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import git

logger = logging.getLogger(__name__)

CPP_EXTENSIONS: frozenset[str] = frozenset(
    {".cpp", ".h", ".hpp", ".cc", ".cxx", ".hxx"}
)

_12_MONTHS_DAYS = 365


@dataclass
class SiloEntry:
    """Describes a knowledge silo detected in the repository.

    Attributes:
        file: Relative path to the siloed file.
        sole_contributor: Name of the single contributor active in the window.
        last_commit_date: ISO date string (YYYY-MM-DD) of the most recent commit.
        risk_note: Human-readable description of the silo risk.
    """

    file: str
    sole_contributor: str
    last_commit_date: str
    risk_note: str


class SiloDetector:
    """Detects knowledge silos in a git repository.

    A file is considered a knowledge silo when only one contributor has
    touched it within the last 12 months.

    Args:
        repo_path: Path to the root of the git repository.
    """

    def __init__(self, repo_path: Path) -> None:
        """Initialize SiloDetector.

        Args:
            repo_path: Absolute or relative path to the git repository root.
        """
        self._repo_path = Path(repo_path).resolve()
        self._repo = git.Repo(str(self._repo_path))
        self._now = datetime.now(tz=timezone.utc)
        self._window_start = self._now - timedelta(days=_12_MONTHS_DAYS)

    def detect(self) -> list[SiloEntry]:
        """Identify knowledge silos across all C++ files.

        Returns:
            List of SiloEntry objects for files with a single recent contributor.
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
            if commit_dt < self._window_start:
                continue

            author = commit.author.name or commit.author.email or "unknown"

            for filepath in commit.stats.files:
                if not self._is_cpp_file(filepath):
                    continue

                if filepath not in file_data:
                    file_data[filepath] = {
                        "authors": set(),
                        "commit_dates": [],
                    }

                file_data[filepath]["authors"].add(author)
                file_data[filepath]["commit_dates"].append(commit_dt)

        silos: list[SiloEntry] = []
        for filepath, data in file_data.items():
            if len(data["authors"]) == 1:
                sole = next(iter(data["authors"]))
                latest_dt = max(data["commit_dates"])
                last_date = latest_dt.strftime("%Y-%m-%d")
                silos.append(
                    SiloEntry(
                        file=filepath,
                        sole_contributor=sole,
                        last_commit_date=last_date,
                        risk_note=(
                            f"Only {sole} has modified this file in the last 12 months. "
                            "Bus factor: 1."
                        ),
                    )
                )
                logger.debug("Silo detected: %s (sole contributor: %s)", filepath, sole)

        return silos

    @staticmethod
    def _is_cpp_file(filepath: str) -> bool:
        """Return True if the file has a C++ extension.

        Args:
            filepath: File path string to check.

        Returns:
            True if the extension is in CPP_EXTENSIONS.
        """
        return Path(filepath).suffix.lower() in CPP_EXTENSIONS
