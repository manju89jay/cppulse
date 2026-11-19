"""Simplified SZZ algorithm implementation for cppulse git-miner.

Produces imperfect candidate labels by:
1. Finding commits whose messages contain bug-related keywords.
2. Blaming each changed file's whole parent revision, rather than tracing only
   the lines changed by the fix.
3. Applying an explicit commit-time cutoff to fixes and candidate origins, then
   counting distinct remaining origins per current file.

These heuristics are not proof of defect introduction or predictive accuracy.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import git

from cppulse.errors import ContractError, IntegrityError

from .history import CPP_EXTENSIONS, HistoryScan, is_bug_fix, scan_history

logger = logging.getLogger(__name__)
_BLAME_HEADER = re.compile(r"([0-9a-f]{40}) [1-9][0-9]* [1-9][0-9]*(?: [1-9][0-9]*)?")


class SZZLabeler:
    """Implements whole-parent-file SZZ candidate labels, not proven defects.

    The algorithm:
    1. Identifies bug-fix commits by scanning commit messages for keywords.
    2. For each bug-fix commit, examines which C++ files were changed.
    3. Uses git blame on each whole parent file, including unchanged lines.
    4. Filters fixes and candidate origins by the chosen commit-time cutoff.
    5. Returns a mapping of file -> count of distinct candidate origin commits.

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
        # Object reads stay bound to the selected repository without invoking
        # an ambient-environment-sensitive git cat-file subprocess.
        self._repo = git.Repo(str(self._repo_path), odbt=git.GitDB)
        self._max_fix_commits = max_fix_commits
        self.limitations: list[str] = []
        self.provenance: dict[str, object] = {}
        self.analysis_cutoff: str | None = None

    def label(
        self,
        *,
        history: HistoryScan | None = None,
        cutoff: datetime | None = None,
    ) -> dict[str, int]:
        """Run SZZ analysis and return imperfect candidate-origin counts.

        Args:
            history: Optional existing checked history scan. The behavioral
                metric window is separate and is not implicitly reused here.
            cutoff: Inclusive aware UTC commit-time boundary for bug-fix
                selection and blamed origins. Defaults to invocation time, captured before reading
                history. Historical evaluations must pass their own cutoff.

        Returns:
            Dict mapping relative file path to the number of distinct
            candidate-origin commits found in that file's blamed parent revisions.
            Returns an empty dict for repos with no commits.

        Raises:
            ContractError: If the explicit cutoff is not an aware UTC datetime.
        """
        selected_cutoff = datetime.now(timezone.utc) if cutoff is None else cutoff
        if (
            not isinstance(selected_cutoff, datetime)
            or selected_cutoff.tzinfo is None
            or selected_cutoff.utcoffset() != timezone.utc.utcoffset(selected_cutoff)
        ):
            raise ContractError("SZZ cutoff must be an aware UTC datetime")
        cutoff_epoch = selected_cutoff.timestamp()
        self.analysis_cutoff = selected_cutoff.isoformat().replace("+00:00", "Z")
        scan = history if history is not None else scan_history(self._repo)
        from .history_cache import HistoryOptions

        owner = scan._cache_owner
        options = owner.options if owner is not None else HistoryOptions.from_document()
        if owner is not None and (
            Path(owner.repo.git_dir).resolve() != Path(self._repo.git_dir).resolve()
            or Path(owner.repo.common_dir).resolve() != Path(self._repo.common_dir).resolve()
        ):
            raise ContractError("SZZ shared history belongs to a different repository")
        self.limitations = list(scan.limitations)
        provenance_notes = [
            f"SZZ bug-fix selection analysis cutoff (inclusive UTC): {self.analysis_cutoff}.",
            "SZZ provenance: keyword-selected bug-fix messages and blame of the whole parent file, "
            "not only changed lines; imperfect candidate labels, not validated future-defect predictions.",
            "Git timestamps are repository metadata, not authenticated observation times; "
            "historical evaluation requires an explicit SZZ cutoff and an independently controlled holdout.",
        ]
        self.provenance = {
            "profile": "szz-keyword-whole-parent-file/1",
            "method": "keyword_selected_bug_fix_parent_blame",
            "analysis_cutoff": self.analysis_cutoff,
            "cutoff_basis": "git_committed_date",
            "cutoff_inclusive": True,
            "cutoff_source": "invocation_time" if cutoff is None else "explicit",
            "label_kind": "imperfect_candidate",
            "blame_scope": "whole_parent_file",
            "max_fix_commits": self._max_fix_commits,
            "skipped_post_cutoff_fix_commits_encountered": 0,
            "filtered_post_cutoff_origin_commits": 0,
            "unavailable_origin_commits": 0,
            "origin_max_record_bytes": options.max_record_bytes,
            "limitations": provenance_notes,
        }
        self._history_owner = scan._cache_owner
        selected: set[str] = set()
        skipped_post_cutoff = 0
        for commit in scan.commits:
            if not self._is_bug_fix(commit.message):
                continue
            if commit.committed_date > cutoff_epoch:
                skipped_post_cutoff += 1
                continue
            if (
                self._max_fix_commits is not None
                and len(selected) >= self._max_fix_commits
            ):
                self.limitations.append(
                    f"SZZ analysis capped at {self._max_fix_commits} most recent bug-fix commits."
                )
                break
            selected.add(commit.hexsha)
        if skipped_post_cutoff:
            provenance_notes.append(
                f"SZZ skipped {skipped_post_cutoff} post-cutoff bug-fix commits "
                "encountered before the tracing cap; these do not consume that cap."
            )
        self.provenance["skipped_post_cutoff_fix_commits_encountered"] = skipped_post_cutoff
        bug_introducing: dict[str, set[str]] = {}
        # A direct object lookup is memoized per distinct observed origin. This
        # does not walk history again or materialize the shared history stream.
        origin_dates: dict[str, int | None] = {}
        filtered_origins: set[str] = set()
        for change in scan.changes:
            if (
                change.commit.hexsha not in selected
                or change.parent_file is None
                or not change.commit.parents
            ):
                continue
            introducing = self._blame_file(change.commit.parents[0], change.parent_file)
            eligible_origins: set[str] = set()
            for sha in sorted(introducing):
                if sha not in origin_dates:
                    failure_reason = "origin object or commit time could not be read"
                    try:
                        info = self._repo.odb.info(bytes.fromhex(sha))
                        if info.type != b"commit":
                            failure_reason = "origin object is not a commit"
                            raise IntegrityError("SZZ origin is not a commit object")
                        if info.size > options.max_record_bytes:
                            failure_reason = "metadata exceeds max_record_bytes"
                            raise IntegrityError("Origin metadata exceeds max_record_bytes")
                        committed_date = self._repo.commit(sha).committed_date
                        if type(committed_date) is not int:
                            failure_reason = "origin commit timestamp is invalid"
                            raise ValueError("Origin commit time is not an integer")
                        origin_dates[sha] = committed_date
                    except (
                        git.BadName, git.BadObject, git.GitCommandError,
                        ValueError, UnicodeError, OSError, IndexError, OverflowError,
                    ) as exc:
                        origin_dates[sha] = None
                        self.limitations.append(
                            f"SZZ origin metadata unavailable for {sha[:8]}; "
                            f"candidate omitted: {failure_reason}."
                        )
                        logger.debug("SZZ origin lookup failed for %s: %s", sha[:8], exc)
                origin_date = origin_dates[sha]
                if origin_date is None:
                    continue
                if origin_date > cutoff_epoch:
                    filtered_origins.add(sha)
                    continue
                eligible_origins.add(sha)
            if eligible_origins:
                bug_introducing.setdefault(change.file, set()).update(eligible_origins)
        self.provenance["filtered_post_cutoff_origin_commits"] = len(filtered_origins)
        self.provenance["unavailable_origin_commits"] = sum(
            value is None for value in origin_dates.values()
        )
        if filtered_origins:
            provenance_notes.append(
                f"SZZ omitted {len(filtered_origins)} distinct post-cutoff origin commits; "
                "ancestor order does not establish monotonic Git timestamps."
            )
        return {path: len(shas) for path, shas in sorted(bug_introducing.items())}

    def _blame_file(self, commit: git.Commit, filepath: str) -> set[str]:
        """Return actual porcelain-header origin SHAs for a whole parent file.

        Runs ``git blame`` on *filepath* at *commit* and collects the SHA of
        every line's origin commit. Tab-prefixed source text cannot become a
        header, even when it contains an existing 40-hex commit identity.

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
            owner = getattr(self, "_history_owner", None)
            if owner is not None:
                blame_output = owner.blame(commit.hexsha, filepath)
            else:
                from .history_cache import HistoryDatabase, HistoryOptions

                temporary_owner = HistoryDatabase(
                    self._repo, HistoryOptions.from_document()
                )
                try:
                    blame_output = temporary_owner.blame(commit.hexsha, filepath)
                finally:
                    temporary_owner.close()

        except (git.GitCommandError, ValueError, UnicodeError) as exc:
            self.limitations.append(
                f"SZZ blame unavailable for {filepath} at {commit.hexsha[:8]}."
            )
            logger.debug(
                "Blame failed for %s at %s: %s", filepath, commit.hexsha[:8], exc
            )
            return set()

        shas: set[str] = set()
        # Porcelain frames use LF. Other control characters can occur inside
        # source text and must not acquire a fresh header boundary.
        for line in blame_output.split("\n"):
            header = _BLAME_HEADER.fullmatch(line)
            if header is not None:
                shas.add(header.group(1))

        return shas

    @staticmethod
    def _is_bug_fix(message: str) -> bool:
        """Return True if the commit message contains a bug-related keyword.

        Args:
            message: Commit message text.

        Returns:
            True if any BUG_KEYWORDS appear (case-insensitive).
        """
        return is_bug_fix(message)

    @staticmethod
    def _is_cpp_file(filepath: str) -> bool:
        """Return True if the file has a C++ extension.

        Args:
            filepath: File path string to check.

        Returns:
            True if the extension is in CPP_EXTENSIONS.
        """
        return Path(filepath).suffix.lower() in CPP_EXTENSIONS
