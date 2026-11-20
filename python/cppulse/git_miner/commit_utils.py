"""Shared helpers for robust git history traversal."""

from __future__ import annotations

import logging
from typing import Any

import git

logger = logging.getLogger(__name__)


def changed_files(commit: git.Commit) -> dict[str, dict[str, Any]]:
    """Return the per-file diff stats for a commit, or {} if unavailable.

    ``commit.stats`` diffs the commit against its first parent. On a shallow
    clone the oldest (boundary) commit's parent object is absent from the
    truncated history, so the diff raises ``GitCommandError`` ("bad object").
    Such commits are skipped — returning an empty mapping — so a single
    boundary commit does not abort traversal of the entire history.

    Args:
        commit: The commit whose changed files to retrieve.

    Returns:
        Mapping of file path to its stat dict (insertions/deletions/lines),
        or an empty mapping when stats cannot be computed.
    """
    try:
        return commit.stats.files
    except (git.GitCommandError, ValueError) as exc:
        logger.debug(
            "Stats unavailable for %s (shallow-clone boundary?): %s",
            commit.hexsha[:8],
            exc,
        )
        return {}
