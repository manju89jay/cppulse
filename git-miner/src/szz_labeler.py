"""Simplified SZZ algorithm implementation for cppulse git-miner.

Identifies bug-introducing commits by:
1. Finding commits whose messages contain bug-related keywords.
2. For each changed file in those commits, tracing back via git blame
   to find the commits that introduced the lines that were changed.
3. Counting how many times each file was touched by bug-introducing commits.
"""

from __future__ import annotations

import logging
from pathlib import Path

import git

logger = logging.getLogger(__name__)

CPP_EXTENSIONS: frozenset[str] = frozenset(
    {".cpp", ".h", ".hpp", ".cc", ".cxx", ".hxx"}
)

BUG_KEYWORDS: tuple[str, ...] = ("fix", "bug", "patch", "issue", "crash", "error")


class SZZLabeler:
    """Implements a simplified SZZ algorithm to find bug-introducing commits.

    The algorithm:
    1. Identifies bug-fix commits by scanning commit messages for keywords.
    2. For each bug-fix commit, examines which C++ files were changed.
    3. Uses git blame on the parent commit to find the commits that originally
       introduced the changed lines.
    4. Returns a mapping of file -> count of distinct bug-introducing commits.

    Args:
        repo_path: Path to the root of the git repository.
        max_fix_commits: Upper bound on bug-fix commits to trace via blame
            (newest first). Keeps runtime bounded on large histories;
            None means no limit.
    """

    def __init__(self, repo_path: Path, max_fix_commits: int | None = None) -> None:
        """Initialize SZZLabeler.

        Args:
            repo_path: Absolute or relative path to the git repository root.
            max_fix_commits: Maximum number of bug-fix commits to analyze
                (newest first), or None for no limit.
        """
        self._repo_path = Path(repo_path).resolve()
        self._repo = git.Repo(str(self._repo_path))
        self._max_fix_commits = max_fix_commits

    def label(self) -> dict[str, int]:
        """Run SZZ analysis and return bug-introducing commit counts per file.

        Returns:
            Dict mapping relative file path to the number of distinct
            bug-introducing commits that touched that file.
            Returns an empty dict for repos with no commits.
        """
        try:
            commits = list(self._repo.iter_commits())
        except (ValueError, git.GitCommandError) as exc:
            logger.warning("Could not iterate commits: %s", exc)
            return {}

        if not commits:
            logger.warning("Repository has no commits: %s", self._repo_path)
            return {}

        bug_fix_commits = [c for c in commits if self._is_bug_fix(c.message)]
        if (
            self._max_fix_commits is not None
            and len(bug_fix_commits) > self._max_fix_commits
        ):
            # iter_commits() yields newest first; keep the most recent fixes.
            logger.info(
                "Capping SZZ analysis to the %d most recent of %d bug-fix commits",
                self._max_fix_commits,
                len(bug_fix_commits),
            )
            bug_fix_commits = bug_fix_commits[: self._max_fix_commits]
        logger.debug("Found %d bug-fix commits", len(bug_fix_commits))

        bug_introducing: dict[str, set[str]] = {}

        for fix_commit in bug_fix_commits:
            if not fix_commit.parents:
                # First commit — nothing to blame
                continue

            parent = fix_commit.parents[0]
            changed_files = [
                fp for fp in fix_commit.stats.files if self._is_cpp_file(fp)
            ]

            for filepath in changed_files:
                introducing_shas = self._blame_file(parent, filepath)
                if not introducing_shas:
                    continue

                if filepath not in bug_introducing:
                    bug_introducing[filepath] = set()
                bug_introducing[filepath].update(introducing_shas)

        return {fp: len(shas) for fp, shas in bug_introducing.items()}

    def _blame_file(self, commit: git.Commit, filepath: str) -> set[str]:
        """Return the set of commit SHAs that introduced lines in a file.

        Runs ``git blame`` on *filepath* at *commit* and collects the SHA of
        every line's origin commit.

        Args:
            commit: The commit object to blame from (typically the parent of the
                    bug-fix commit).
            filepath: Relative path to the file within the repository.

        Returns:
            Set of commit SHA strings found in the blame output.
            Returns an empty set if the file does not exist at that commit or
            if blame fails.
        """
        try:
            blame_output = self._repo.git.blame(
                commit.hexsha,
                "--porcelain",
                "--",
                filepath,
            )
        except git.GitCommandError as exc:
            logger.debug(
                "Blame failed for %s at %s: %s", filepath, commit.hexsha[:8], exc
            )
            return set()

        shas: set[str] = set()
        for line in blame_output.splitlines():
            parts = line.split()
            if (
                parts
                and len(parts[0]) == 40
                and all(c in "0123456789abcdef" for c in parts[0])
            ):
                shas.add(parts[0])

        return shas

    @staticmethod
    def _is_bug_fix(message: str) -> bool:
        """Return True if the commit message contains a bug-related keyword.

        Args:
            message: Commit message text.

        Returns:
            True if any BUG_KEYWORDS appear (case-insensitive).
        """
        lower = message.lower()
        return any(keyword in lower for keyword in BUG_KEYWORDS)

    @staticmethod
    def _is_cpp_file(filepath: str) -> bool:
        """Return True if the file has a C++ extension.

        Args:
            filepath: File path string to check.

        Returns:
            True if the extension is in CPP_EXTENSIONS.
        """
        return Path(filepath).suffix.lower() in CPP_EXTENSIONS
