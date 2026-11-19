"""Project recorded history onto current tracked C++ file identities.

Rename attribution is deterministic for linear history. Merge histories retain
first-parent deltas but are explicitly marked partial because lineage across
branches is not a proven knowledge/ownership model.
"""

from __future__ import annotations

import re
import hashlib
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from pathlib import Path

import git

from cppulse.errors import IntegrityError
from cppulse.execution import ProcessLimits, run_bounded_process

HISTORY_PROJECTION_IMPORT_SHA256 = hashlib.sha256(
    Path(__file__).read_bytes()
).hexdigest()

MAX_INVENTORY_BYTES = 64 * 1024 * 1024
MAX_TRACKED_PATHS = 1_000_000
MAX_TRACKED_PATH_BYTES = 64 * 1024
READ_ONLY_GIT_OPTIONS: tuple[str, ...] = (
    "--no-pager",
    "--literal-pathspecs",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.attributesFile=/dev/null",
    "-c",
    "core.untrackedCache=false",
    "-c",
    "core.preloadIndex=false",
    "-c",
    "gc.auto=0",
)

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
    commits: Sequence[Any] = field(default_factory=list)
    changes: Iterable[HistoryChange] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    commit_file_counts: Mapping[str, int] = field(default_factory=dict)
    cache_info: dict[str, Any] = field(default_factory=dict)
    _cache_owner: Any = field(default=None, repr=False)


def is_bug_fix(message: str) -> bool:
    """Match bug-related words, avoiding unrelated fixture/prefix substrings."""
    return BUG_PATTERN.search(message) is not None


def selected_git_environment(repo: git.Repo) -> dict[str, str]:
    """Bind Git commands to the selected repository, independent of caller overrides."""
    common = Path(repo.common_dir).resolve()
    directory = Path(repo.git_dir).resolve()
    environment = {
        "GIT_DIR": str(directory),
        "GIT_COMMON_DIR": str(common),
        "GIT_WORK_TREE": str(Path(repo.working_tree_dir or repo.git_dir).resolve()),
        "GIT_INDEX_FILE": str(directory / "index"),
        "GIT_OBJECT_DIRECTORY": str(common / "objects"),
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": "",
        "GIT_NAMESPACE": "",
        "GIT_SHALLOW_FILE": str(common / "shallow"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_COUNT": "0",
        "GIT_CONFIG_PARAMETERS": "",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_ATTR_SOURCE": "",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_TRACE": "",
        "GIT_TRACE2": "",
        "GIT_TRACE2_EVENT": "",
        "GIT_TRACE2_PERF": "",
        "GIT_TRACE_SETUP": "",
        "GIT_TRACE_PERFORMANCE": "",
        "GIT_TRACE_PACK_ACCESS": "",
        "GIT_TRACE_PACKET": "",
        "GIT_TRACE_CURL": "",
        "GIT_CURL_VERBOSE": "",
        "GIT_PREFIX": "",
        "LC_ALL": "C",
    }

    # Trace destinations are open-ended across Git versions. Mask every ambient
    # trace key, rather than silently allowing a newly supported destination.
    environment.update({key: "" for key in os.environ if key.startswith("GIT_TRACE")})
    return environment


def _tracked_paths(repo: git.Repo, timeout_seconds: float) -> Iterable[str]:
    executable = shutil.which("git")
    if executable is None:
        raise IntegrityError("Git inventory executable is unavailable")
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        outcome = run_bounded_process(
            [executable, *READ_ONLY_GIT_OPTIONS, "ls-files", "-z", "--cached"],
            cwd=Path(repo.working_tree_dir or repo.git_dir),
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=timeout_seconds,
            limits=ProcessLimits(
                max_log_bytes=MAX_INVENTORY_BYTES, termination_grace_seconds=0.2
            ),
            environment=selected_git_environment(repo),
        )
        if (
            outcome.status != "passed"
            or outcome.stdout_bytes + outcome.stderr_bytes > outcome.captured_bytes
        ):
            raise IntegrityError(
                "Git inventory failed, timed out or exceeded its bounded capture"
            )
        stdout.seek(0)
        pending = b""
        count = 0
        while chunk := stdout.read(64 * 1024):
            fields = (pending + chunk).split(b"\0")
            pending = fields.pop()
            if len(pending) > MAX_TRACKED_PATH_BYTES:
                raise IntegrityError("Git inventory path exceeds its byte bound")
            for raw in fields:
                count += 1
                if count > MAX_TRACKED_PATHS:
                    raise IntegrityError("Git inventory entry count exceeds its bound")
                if not raw or len(raw) > MAX_TRACKED_PATH_BYTES:
                    raise IntegrityError(
                        "Git inventory path is empty or exceeds its byte bound"
                    )
                try:
                    yield raw.decode("utf-8")
                except UnicodeError as exc:
                    raise IntegrityError(
                        "Git inventory path is not representable as UTF-8"
                    ) from exc
        if pending:
            raise IntegrityError("Git inventory has a truncated path record")


def current_cpp_files(
    repo: git.Repo, limitations: list[str] | None = None, *, timeout_seconds: float = 60
) -> set[str]:
    """Return finite, selected-index tracked regular C++ inputs without helpers.

    The inventory command has a 64 MiB combined capture budget and at most one
    million records, each at most 64 KiB. Caller Git root/index/config overrides
    are masked; repository fsmonitor hooks and lazy fetching are disabled.
    Excluded symlinks and unresolved/outside paths retain visible limitations.
    """
    if repo.working_tree_dir is None:
        return set()
    notes = limitations if limitations is not None else []
    root = Path(repo.working_tree_dir).resolve()
    current: set[str] = set()
    for name in _tracked_paths(repo, timeout_seconds):
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


def scan_history(
    repo: git.Repo, *, options: Any = None, revision: str | None = None
) -> HistoryScan:
    """Stream checked raw facts once and replay current-file rename projection.

    Optional persistent cache checkpoints preserve immutable raw commit facts;
    current tracked scope is independently rediscovered on every invocation.
    """
    from .history_cache import HistoryDatabase, HistoryOptions

    if isinstance(options, HistoryOptions):
        document = asdict(options)
        if document["cache_dir"] is not None:
            document["cache_dir"] = str(document["cache_dir"])
        selected = HistoryOptions.from_document(document)
    else:
        selected = HistoryOptions.from_document(options)
    notes: list[str] = []
    files = current_cpp_files(repo, notes, timeout_seconds=selected.timeout_seconds)
    owner = HistoryDatabase(repo, selected)
    return owner.open_scan(files, notes, revision=revision)
