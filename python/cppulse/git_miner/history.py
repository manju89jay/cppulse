"""Project recorded history onto current tracked C++ file identities.

Rename attribution is deterministic for linear history. Merge histories retain
first-parent deltas but are explicitly marked partial because lineage across
branches is not a proven knowledge/ownership model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import git

CPP_EXTENSIONS: frozenset[str] = frozenset(
    {".cpp", ".h", ".hpp", ".cc", ".cxx", ".hxx", ".hh", ".ipp", ".inl", ".tpp"}
)
BUG_PATTERN = re.compile(
    r"\b(?:fix(?:e[ds]|ing|es)?|bugs?|patch(?:es|ed|ing)?|issues?|crash(?:es|ed|ing)?|errors?)\b",
    re.IGNORECASE,
)


@dataclass
class HistoryChange:
    """One first-parent change attributed to an existing current file."""

    file: str
    parent_file: str | None
    commit: git.Commit
    insertions: int
    deletions: int


@dataclass
class HistoryScan:
    """Current file inventory and usable history facts with explicit limits."""

    files: set[str] = field(default_factory=set)
    commits: list[git.Commit] = field(default_factory=list)
    changes: list[HistoryChange] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def is_bug_fix(message: str) -> bool:
    """Match bug-related words, avoiding unrelated fixture/prefix substrings."""
    return BUG_PATTERN.search(message) is not None


def current_cpp_files(repo: git.Repo, limitations: list[str] | None = None) -> set[str]:
    """Return current tracked regular C++ inputs without following symlinks.

    Every component below the selected worktree root is checked, since a
    regular-looking leaf may otherwise be reached through a directory symlink.
    Excluded links and unresolved/outside paths remain visible limitations.
    """
    if repo.working_tree_dir is None:
        return set()
    notes = limitations if limitations is not None else []
    root = Path(repo.working_tree_dir).resolve()
    current: set[str] = set()
    for name in repo.git.ls_files("-z").split("\0"):
        path = Path(name)
        if not name or path.suffix.lower() not in CPP_EXTENSIONS:
            continue
        if path.is_absolute() or ".." in path.parts:
            notes.append(f"Skipped tracked path outside selected root: {name}.")
            continue
        cursor = root
        for part in path.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                notes.append(f"Skipped tracked symlink path: {name}.")
                break
        else:
            try:
                resolved = (root / path).resolve(strict=True)
                if not resolved.is_relative_to(root):
                    notes.append(f"Skipped tracked path outside selected root: {name}.")
                elif resolved.is_file():
                    current.add(name)
            except FileNotFoundError:
                # A worktree deletion is not part of current source scope.
                continue
            except OSError:
                notes.append(f"Could not resolve tracked source path: {name}.")
    return current


def scan_history(repo: git.Repo) -> HistoryScan:
    """Trace current file names backwards through recorded rename boundaries.

    A new-file addition terminates that name's lineage, so deleted/recreated
    files cannot inherit an unrelated older file's history. Unavailable parent
    objects and merge-lineage assumptions remain explicit limitations.
    """
    result = HistoryScan()
    result.files = current_cpp_files(repo, result.limitations)
    try:
        result.commits = list(repo.iter_commits())
    except (ValueError, git.GitCommandError):
        result.limitations.append("Repository has no readable commit history.")
        return result
    if repo.git.rev_parse("--is-shallow-repository").strip() == "true":
        result.limitations.append(
            "Shallow history: earlier changes and contributors are unavailable."
        )
    aliases = {name: name for name in result.files}
    for commit in result.commits:
        try:
            if len(commit.parents) > 1:
                note = "Merge history uses first-parent deltas; cross-branch rename lineage is not verified."
                if note not in result.limitations:
                    result.limitations.append(note)
            diffs = (
                commit.parents[0].diff(commit, create_patch=True, M=True)
                if commit.parents
                else commit.diff(git.NULL_TREE, create_patch=True, M=True)
            )
        except (git.GitCommandError, ValueError, OSError) as exc:
            result.limitations.append(
                f"History delta unavailable for {commit.hexsha[:8]}: {type(exc).__name__}."
            )
            continue
        # Compute every destination before mutating aliases: rename swaps must
        # not make one change accidentally inherit another change's identity.
        destinations = [(diff, aliases.get(diff.b_path)) for diff in diffs]
        updates: list[tuple[str | None, str | None, str]] = []
        for diff, current in destinations:
            if current is None:
                continue
            patch = diff.diff
            if isinstance(patch, str):
                patch = patch.encode("utf-8", errors="replace")
            if patch.startswith(b"Binary files"):
                result.limitations.append(
                    f"Binary history statistics unavailable for {current}."
                )
            lines = patch.splitlines()
            result.changes.append(
                HistoryChange(
                    file=current,
                    parent_file=diff.a_path,
                    commit=commit,
                    insertions=sum(line.startswith(b"+") for line in lines),
                    deletions=sum(line.startswith(b"-") for line in lines),
                )
            )
            if diff.new_file or diff.renamed_file:
                updates.append((diff.b_path, diff.a_path, current))
        for destination, original, current in updates:
            aliases.pop(destination, None)
        for destination, original, current in updates:
            if original is not None:
                aliases[original] = current
    return result
