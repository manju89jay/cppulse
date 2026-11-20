"""Checked, streamed Git raw facts and durable local mining checkpoints.

Cache rows identify immutable Git commits, not current source execution or
verification receipts. Derived metrics and rename projection are recomputed for
current scope; aliases, windows and policy choices never become raw fact keys.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from functools import lru_cache
from importlib import resources
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from uuid import uuid4
from typing import Any

import git
import jsonschema

from cppulse.errors import ContractError, IntegrityError
from cppulse.execution import ProcessLimits, run_bounded_process
from cppulse.identities import digest_json

PROFILE = "cppulse-git-raw-1"
_COLLECTOR_IMPORT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_RAW_SCHEMA_IMPORT_SHA256 = hashlib.sha256(
    resources.files("cppulse.contracts")
    .joinpath("schemas", "git_history_private", "raw_commit.schema.json")
    .read_bytes()
).hexdigest()
_SHA = re.compile(r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")


@lru_cache(maxsize=4)
def _validator(name: str) -> jsonschema.Draft7Validator:
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas", "git_history_private", name + ".schema.json")
        .read_text()
    )
    return jsonschema.Draft7Validator(schema)


def validate_history_document(kind: str, document: dict[str, Any]) -> None:
    """Validate a finite private cache contract without opening Git or cache files."""
    if kind not in {"raw_commit", "options", "checkpoint", "result"}:
        raise ContractError("Unsupported private Git history document")
    try:
        json.dumps(document, allow_nan=False)
        _validator(kind).validate(document)
    except (ValueError, TypeError, jsonschema.ValidationError) as error:
        raise ContractError(f"Invalid Git history {kind}: {error}") from error


@dataclass(frozen=True)
class HistoryOptions:
    """Explicit raw history bounds and optional authorized persistent cache."""

    cache_dir: Path | None = None
    max_commits: int = 100000
    max_record_bytes: int = 8388608
    max_cache_bytes: int = 268435456
    timeout_seconds: float = 60

    @classmethod
    def from_document(cls, value: Mapping[str, Any] | None = None) -> HistoryOptions:
        """Validate options before any repository or cache operation."""
        if value is not None and not isinstance(value, Mapping):
            raise ContractError("History options must be an object")
        document = dict(value or {})
        validate_history_document("options", document)
        if set(document) - {
            "cache_dir",
            "max_commits",
            "max_record_bytes",
            "max_cache_bytes",
            "timeout_seconds",
        }:
            raise ContractError("Unsupported history option")
        if document.get("cache_dir") is not None:
            if (
                not isinstance(document["cache_dir"], str)
                or not document["cache_dir"].strip()
                or "\x00" in document["cache_dir"]
            ):
                raise ContractError(
                    "History cache_dir must be a nonblank explicit path"
                )
            document["cache_dir"] = Path(document["cache_dir"])
        result = cls(**document)
        for name, low, high in [
            ("max_commits", 1, 1000000),
            ("max_record_bytes", 1024, 67108864),
            ("max_cache_bytes", 1048576, 8589934592),
        ]:
            value = getattr(result, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not low <= value <= high
            ):
                raise ContractError(
                    f"History {name} must be an integer in [{low}, {high}]"
                )
        if (
            isinstance(result.timeout_seconds, bool)
            or not isinstance(result.timeout_seconds, (int, float))
            or not math.isfinite(result.timeout_seconds)
            or not 1 <= result.timeout_seconds <= 3600
        ):
            raise ContractError("History timeout_seconds must be finite in [1,3600]")
        return result


def _bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
        or PurePosixPath(value).as_posix() != value
        or ".." in PurePosixPath(value).parts
    ):
        raise ContractError("Raw Git paths must be canonical relative POSIX identities")
    return value


def validate_raw_record(record: dict[str, Any]) -> None:
    """Validate a raw record independently from cache acceptance and projection."""
    validate_history_document("raw_commit", record)
    expected = {
        "version",
        "commit_id",
        "parents",
        "author",
        "committed_date",
        "message",
        "changes",
        "total_files",
        "available",
        "limitations",
    }
    if (
        set(record) != expected
        or record["version"] != "1.0.0"
        or not _SHA.fullmatch(record["commit_id"])
    ):
        raise ContractError("Invalid raw history record identity/version")
    if not isinstance(record["parents"], list) or any(
        not isinstance(sha, str) or not _SHA.fullmatch(sha) for sha in record["parents"]
    ):
        raise ContractError("Invalid raw commit parent identities")
    if (
        set(record["author"]) != {"name", "email"}
        or any(not isinstance(v, str) for v in record["author"].values())
        or not isinstance(record["message"], str)
    ):
        raise ContractError("Invalid raw commit attribution/message")
    if (
        isinstance(record["committed_date"], bool)
        or not isinstance(record["committed_date"], int)
        or not -62135596800 <= record["committed_date"] <= 253402300799
    ):
        raise ContractError("Invalid raw commit timestamp")
    if (
        not isinstance(record["available"], bool)
        or not isinstance(record["limitations"], list)
        or any(not isinstance(v, str) or not v for v in record["limitations"])
    ):
        raise ContractError("Invalid raw commit availability/limitations")
    if not isinstance(record["changes"], list) or record["total_files"] != len(
        record["changes"]
    ):
        raise ContractError("Raw changed-file inventory count differs")
    seen = set()
    for row in record["changes"]:
        if set(row) != {
            "old_path",
            "new_path",
            "status",
            "insertions",
            "deletions",
            "binary",
        } or row["status"] not in {"A", "M", "D", "R", "C", "T", "U"}:
            raise ContractError("Invalid raw change record")
        for field in ["old_path", "new_path"]:
            if row[field] is not None:
                _path(row[field])
        if row["old_path"] is None and row["new_path"] is None:
            raise ContractError("A raw change needs a path identity")
        key = (row["old_path"], row["new_path"])
        if key in seen:
            raise ContractError("Duplicate raw changed-file cell")
        seen.add(key)
        if any(
            isinstance(row[k], bool) or not isinstance(row[k], int) or row[k] < 0
            for k in ["insertions", "deletions"]
        ) or not isinstance(row["binary"], bool):
            raise ContractError("Invalid raw line-count facts")
    if not record["available"] and (record["changes"] or not record["limitations"]):
        raise ContractError(
            "Unavailable raw delta needs an explicit reason and cannot claim changes"
        )


def _accepted_checkpoint(commit_id: str) -> None:
    """Private interruption seam after durable accepted-record publication."""


def _safe_root(root: Path, git_dir: Path) -> None:
    canonical = Path(os.path.abspath(root))
    if canonical == git_dir or canonical.is_relative_to(git_dir):
        raise IntegrityError("History cache must be outside Git metadata")
    for parent in [*reversed(root.parents), root]:
        if parent.is_symlink():
            raise IntegrityError("History cache ancestors cannot be symlinks")
        if parent.exists() and not parent.is_dir():
            raise IntegrityError("History cache needs regular directories")
    root.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ParentCommit:
    """A retained parent object identity for blame without reloading history."""

    hexsha: str


@dataclass(frozen=True)
class StoredCommit:
    """Read-only shared commit metadata with the producer's existing interface."""

    hexsha: str
    committed_date: int
    author: git.Actor
    message: str
    parents: tuple[ParentCommit, ...]


def _commit(record: dict[str, Any]) -> StoredCommit:
    return StoredCommit(
        record["commit_id"],
        record["committed_date"],
        git.Actor(record["author"]["name"], record["author"]["email"]),
        record["message"],
        tuple(ParentCommit(sha) for sha in record["parents"]),
    )


def _parse_delta(content: bytes) -> list[dict[str, Any]]:
    fields = content.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    changes = []
    position = 0
    while position < len(fields) and fields[position].startswith(b":"):
        header = fields[position].split()
        position += 1
        if len(header) != 5:
            raise ContractError("Malformed raw Git delta header")
        status = header[-1][:1].decode("ascii")
        if position >= len(fields):
            raise ContractError("Missing raw Git delta path")
        old = _path(fields[position].decode("utf-8"))
        position += 1
        new = old
        if status in {"R", "C"}:
            if position >= len(fields):
                raise ContractError("Missing raw rename destination")
            new = _path(fields[position].decode("utf-8"))
            position += 1
        elif status == "A":
            old = None
        elif status == "D":
            new = None
        changes.append(
            {
                "old_path": old,
                "new_path": new,
                "status": status,
                "insertions": 0,
                "deletions": 0,
                "binary": False,
            }
        )
    single = {
        row["new_path"] or row["old_path"]: row
        for row in changes
        if row["status"] not in {"R", "C"}
    }
    renamed = {
        (row["old_path"], row["new_path"]): row
        for row in changes
        if row["status"] in {"R", "C"}
    }
    consumed = set()
    while position < len(fields):
        parts = fields[position].split(b"\t", 2)
        position += 1
        if len(parts) != 3:
            raise ContractError("Malformed raw Git numstat record")
        if parts[2]:
            path = _path(parts[2].decode("utf-8"))
            row = single.get(path)
        else:
            if position + 1 >= len(fields):
                raise ContractError("Missing numstat rename identities")
            old = _path(fields[position].decode("utf-8"))
            new = _path(fields[position + 1].decode("utf-8"))
            position += 2
            row = renamed.get((old, new))
        if row is None or id(row) in consumed:
            raise ContractError("Git raw/numstat identities disagree")
        consumed.add(id(row))
        binary = parts[0] == b"-" or parts[1] == b"-"
        row.update(
            binary=binary,
            insertions=0 if binary else int(parts[0]),
            deletions=0 if binary else int(parts[1]),
        )
    if len(consumed) != len(changes):
        raise ContractError("Git raw delta lacks matching numstat counts")
    return changes


class HistoryDatabase:
    """Local SQLite derived cache with bounded rows and transactional checkpoints."""

    def __init__(self, repo: git.Repo, options: HistoryOptions) -> None:
        repo = git.Repo(repo.working_tree_dir or repo.git_dir, odbt=git.GitDB)
        self.repo = repo
        from .history import READ_ONLY_GIT_OPTIONS, selected_git_environment

        self.environment = selected_git_environment(repo)
        self.read_only_options = READ_ONLY_GIT_OPTIONS
        self.options = options
        self.temporary = None
        self.cwd = Path(repo.working_tree_dir or repo.git_dir).absolute()
        if options.cache_dir is None:
            self.temporary = tempfile.TemporaryDirectory(prefix="cppulse-history-")
            self.root = Path(self.temporary.name)
        else:
            self.root = (
                (self.cwd / options.cache_dir).absolute()
                if not options.cache_dir.is_absolute()
                else options.cache_dir.absolute()
            )
        _safe_root(self.root, Path(repo.common_dir).resolve())
        self.root = Path(os.path.abspath(self.root))
        self.path = self.root / "history-v1.sqlite3"
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise IntegrityError("Unsafe history cache database path")
        existed = self.path.exists()
        if existed and self.path.stat().st_nlink != 1:
            raise IntegrityError("Mutable history cache cannot be a hard link")
        if existed and self.path.stat().st_size > options.max_cache_bytes:
            raise IntegrityError(
                "Existing history cache exceeds requested actual file byte budget"
            )
        for suffix in ["-journal", "-wal", "-shm"]:
            sibling = self.path.with_name(self.path.name + suffix)
            if sibling.is_symlink() or (
                sibling.exists()
                and (
                    not sibling.is_file()
                    or sibling.stat().st_nlink != 1
                    or sibling.stat().st_size > 2 * options.max_cache_bytes
                )
            ):
                raise IntegrityError(
                    "Unsafe or over-bound history cache journal sidecar"
                )
        self.db = sqlite3.connect(self.path, timeout=2)
        if existed:
            try:
                magic = self.db.execute(
                    "SELECT value FROM meta WHERE key='format'"
                ).fetchone()
            except sqlite3.DatabaseError as error:
                self.db.close()
                raise IntegrityError(
                    "Existing history cache has an unknown/corrupt format"
                ) from error
            if magic != ("cppulse-git-history-cache-1",):
                self.db.close()
                raise IntegrityError("Existing database is not a cppulse history cache")
        if existed and self.db.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
            self.db.close()
            raise IntegrityError(
                "History cache requires DELETE journaling; explicit migration is needed"
            )
        # PRAGMA page_size cannot change an existing database without VACUUM.
        # Enforce the actual on-disk page size before any mutating pragma.
        actual_page_size = self.db.execute("PRAGMA page_size").fetchone()[0]
        current_pages = self.db.execute("PRAGMA page_count").fetchone()[0]
        if (
            current_pages * actual_page_size > options.max_cache_bytes
            or self.path.stat().st_size > options.max_cache_bytes
        ):
            self.db.close()
            raise IntegrityError("Existing history cache exceeds requested byte budget")
        self.db.execute(
            f"PRAGMA max_page_count={options.max_cache_bytes//actual_page_size}"
        )
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA cache_size=-4096")
        self.db.executescript(
            """
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS raw_records(profile TEXT NOT NULL,commit_id TEXT NOT NULL,payload BLOB NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(profile,commit_id));
        CREATE TABLE IF NOT EXISTS views(id TEXT PRIMARY KEY,request TEXT NOT NULL,selection TEXT NOT NULL,selection_sha TEXT NOT NULL,state TEXT NOT NULL,descriptor TEXT,descriptor_sha TEXT);
        CREATE TABLE IF NOT EXISTS view_records(view_id TEXT NOT NULL,ordinal INTEGER NOT NULL,commit_id TEXT NOT NULL,record_sha TEXT,PRIMARY KEY(view_id,ordinal),UNIQUE(view_id,commit_id));
        CREATE TABLE IF NOT EXISTS projections(id TEXT PRIMARY KEY,view_id TEXT NOT NULL,descriptor TEXT,descriptor_sha TEXT);
        CREATE TABLE IF NOT EXISTS projected_changes(projection_id TEXT NOT NULL,ordinal INTEGER NOT NULL,payload BLOB NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(projection_id,ordinal));
        """
        )
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO meta VALUES('format','cppulse-git-history-cache-1')"
            )
        self.extracted = self.reused = self.recovered = 0
        self.traversals = 0
        self.executable = shutil.which("git")
        if self.executable is None:
            raise ContractError("Git executable is unavailable")
        version = self._command(["--version"], 65536).decode("utf-8").strip()
        if (Path(repo.common_dir) / "info/grafts").exists():
            raise ContractError(
                "Legacy Git grafts are unsupported by checked history; replace them explicitly before mining"
            )
        parsed_version = re.match(r"git version (\d+)\.(\d+)", version)
        if parsed_version is None or tuple(map(int, parsed_version.groups())) < (2, 43):
            raise ContractError(
                "Checked history requires Git >=2.43 with explicit commit attribute sources"
            )
        self.shallow = self._shallow()
        self.attributes = self._attribute_identity()
        self.source_materials = self._source_materials()
        binary_hash = hashlib.sha256()
        with Path(self.executable).open("rb") as binary:
            for chunk in iter(lambda: binary.read(1024 * 1024), b""):
                binary_hash.update(chunk)
        self.profile = {
            "method": PROFILE,
            "repository": str(Path(repo.common_dir).resolve()),
            "git_executable": str(Path(self.executable).resolve()),
            "git_version": version,
            "gitpython_version": git.__version__,
            "python_version": list(sys.version_info[:3]),
            "producer_materials": self.source_materials,
            "info_attributes": self.attributes,
            "attribute_source": "selected-commit-tree",
            "git_executable_sha256": binary_hash.hexdigest(),
            "object_replacement": "disabled",
            "diff_algorithm": "myers",
            "shallow": self.shallow,
            "max_record_bytes": options.max_record_bytes,
            "delta_options": [
                "--no-ext-diff",
                "--no-textconv",
                "--raw",
                "--numstat",
                "-z",
                "-r",
                "-M50%",
            ],
            "limits_platform": "posix-process-wall-and-log-bounds",
        }
        self.profile_id = digest_json(self.profile)

    def close(self) -> None:
        """Release local handles and remove an invocation-private spool."""
        if getattr(self, "db", None) is not None:
            self.db.close()
            self.db = None
        if self.temporary is not None:
            self.temporary.cleanup()
            self.temporary = None

    def __del__(self) -> None:
        try:
            self.close()
        except (OSError, sqlite3.Error):
            pass

    def _command(
        self, args: list[str], cap: int, *, allow_failure: bool = False
    ) -> bytes:
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            outcome = run_bounded_process(
                [
                    self.executable,
                    *self.read_only_options,
                    "-c",
                    "diff.renameLimit=100000",
                    "-c",
                    "diff.algorithm=myers",
                    "-c",
                    "core.attributesFile=/dev/null",
                    "-c",
                    "diff.indentHeuristic=false",
                    *args,
                ],
                cwd=self.cwd,
                stdout=stdout,
                stderr=stderr,
                timeout_seconds=self.options.timeout_seconds,
                limits=ProcessLimits(
                    max_log_bytes=min(67108864, cap), termination_grace_seconds=0.2
                ),
                environment=self.environment,
            )
            if (
                outcome.status != "passed"
                or outcome.stdout_bytes + outcome.stderr_bytes > outcome.captured_bytes
            ):
                stderr.seek(0)
                reason = stderr.read(512).decode("utf-8", errors="replace")
                if allow_failure:
                    return b""
                raise IntegrityError(
                    f"Git command unavailable, timed out or exceeded capture bound: {outcome.status}; {reason}"
                )
            stdout.seek(0)
            return stdout.read(cap + 1)

    def _source_materials(self) -> dict[str, str]:
        from .history import HISTORY_PROJECTION_IMPORT_SHA256

        projection = Path(__file__).with_name("history.py").read_bytes()
        collector = Path(__file__).read_bytes()
        if (
            _digest(projection) != HISTORY_PROJECTION_IMPORT_SHA256
            or _digest(collector) != _COLLECTOR_IMPORT_SHA256
        ):
            raise IntegrityError(
                "History producer source changed since import; restart collection"
            )
        raw_schema = (
            resources.files("cppulse.contracts")
            .joinpath("schemas", "git_history_private", "raw_commit.schema.json")
            .read_bytes()
        )
        if _digest(raw_schema) != _RAW_SCHEMA_IMPORT_SHA256:
            raise IntegrityError(
                "Raw history schema changed since import; restart collection"
            )
        return {
            "collector_sha256": _COLLECTOR_IMPORT_SHA256,
            "projection_sha256": HISTORY_PROJECTION_IMPORT_SHA256,
            "raw_schema_sha256": _digest(raw_schema),
        }

    def _attribute_identity(self) -> list[dict[str, str]]:
        results = []
        for directory in sorted(
            {
                str(Path(self.repo.git_dir).resolve()),
                str(Path(self.repo.common_dir).resolve()),
            }
        ):
            path = Path(directory) / "info/attributes"
            if not path.exists():
                results.append({"root": directory, "status": "absent"})
                continue
            if (
                path.is_symlink()
                or not stat.S_ISREG(path.stat().st_mode)
                or path.stat().st_size > self.options.max_record_bytes
            ):
                raise IntegrityError(
                    "Git info/attributes is unsafe or exceeds its finite bound"
                )
            before = path.stat()
            with path.open("rb") as stream:
                content = stream.read(self.options.max_record_bytes + 1)
            after = path.stat()
            if len(content) > self.options.max_record_bytes or (
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (after.st_ino, after.st_size, after.st_mtime_ns):
                raise IntegrityError("Git info/attributes changed while observed")
            results.append(
                {"root": directory, "status": "available", "sha256": _digest(content)}
            )
        return results

    def blame(self, commit_id: str, file: str) -> str:
        """Run a bounded selected-repository blame with no project diff driver."""
        if not _SHA.fullmatch(commit_id):
            raise ContractError("Blame requires an explicit commit ID")
        _path(file)
        return self._command(
            [
                "--attr-source=" + commit_id,
                "blame",
                "--no-textconv",
                "--porcelain",
                commit_id,
                "--",
                file,
            ],
            self.options.max_record_bytes,
        ).decode("utf-8")

    def _shallow(self) -> str:
        path = Path(self.repo.common_dir) / "shallow"
        if not path.exists():
            return "full"
        if path.is_symlink() or path.stat().st_size > self.options.max_record_bytes:
            raise IntegrityError("Unsafe or over-bound Git shallow metadata")
        return _digest(path.read_bytes())

    def _request(self, head: str | None) -> dict[str, Any]:
        return {
            "version": "1.0.0",
            "profile_digest": self.profile_id,
            "head": head,
            "max_commits": self.options.max_commits,
        }

    def _selection(self, view_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT selection,selection_sha FROM views WHERE id=?", (view_id,)
        ).fetchone()
        if row is None or _digest(row[0].encode()) != row[1]:
            raise IntegrityError("History selection checkpoint integrity mismatch")
        selected = json.loads(row[0])
        h = hashlib.sha256()
        count = 0
        for ordinal, sha in self.db.execute(
            "SELECT ordinal,commit_id FROM view_records WHERE view_id=? ORDER BY ordinal",
            (view_id,),
        ):
            if ordinal != count or not _SHA.fullmatch(sha):
                raise IntegrityError("History checkpoint order/identity is invalid")
            h.update((sha + "\n").encode())
            count += 1
        if count != selected["count"] or h.hexdigest() != selected["ids_sha256"]:
            raise IntegrityError("History checkpoint selected-commit inventory differs")
        return selected

    def _existing(self, request: dict[str, Any]) -> tuple[str | None, str]:
        request_json = _bytes(request).decode()
        row = self.db.execute(
            "SELECT id,state FROM views WHERE request=? ORDER BY rowid DESC LIMIT 1",
            (request_json,),
        ).fetchone()
        if row:
            try:
                selection = self._selection(row[0])
                if row[1] not in {"building", "ready"}:
                    raise IntegrityError("Unaccepted revision selection cannot resume")
                if row[1] == "ready":
                    stored = self.db.execute(
                        "SELECT descriptor,descriptor_sha FROM views WHERE id=?",
                        (row[0],),
                    ).fetchone()
                    if stored is None or _digest(stored[0].encode()) != stored[1]:
                        raise IntegrityError("Accepted checkpoint descriptor changed")
                    descriptor = json.loads(stored[0])
                    validate_history_document("checkpoint", descriptor)
                    facts_hash = hashlib.sha256()
                    for sha, digest in self.db.execute(
                        "SELECT commit_id,record_sha FROM view_records WHERE view_id=? ORDER BY ordinal",
                        (row[0],),
                    ):
                        if digest is None or not re.fullmatch(r"[a-f0-9]{64}", digest):
                            raise IntegrityError(
                                "Accepted checkpoint contains pending facts"
                            )
                        facts_hash.update((sha + ":" + digest + "\n").encode())
                    if (
                        descriptor["request"] != request
                        or descriptor["selection"] != selection
                        or descriptor["facts_sha256"] != facts_hash.hexdigest()
                    ):
                        raise IntegrityError(
                            "Accepted checkpoint facts/selection differ"
                        )
            except (IntegrityError, ValueError, KeyError, TypeError):
                with self.db:
                    self.db.execute(
                        "DELETE FROM view_records WHERE view_id=?", (row[0],)
                    )
                    self.db.execute("DELETE FROM views WHERE id=?", (row[0],))
                return None, "checkpoint_rebuild"
            return row[0], "warm" if row[1] == "ready" else "resume"
        previous = self.db.execute(
            "SELECT value FROM meta WHERE key='current_view'"
        ).fetchone()
        if previous:
            row = self.db.execute(
                "SELECT request FROM views WHERE id=?", (previous[0],)
            ).fetchone()
            if row:
                old = json.loads(row[0])
                profile = self.db.execute(
                    "SELECT value FROM meta WHERE key='last_profile'"
                ).fetchone()
                old_profile = json.loads(profile[0]) if profile else {}
                if old_profile.get("shallow") != self.shallow:
                    return None, "shallow_rebuild"
                if old.get("profile_digest") != self.profile_id:
                    return None, "profile_rebuild"
                if (
                    old.get("head") != request["head"]
                    and old.get("head")
                    and request["head"]
                ):
                    # --is-ancestor writes no output for either outcome; ask a
                    # bounded merge-base equality instead of guessing from text.
                    base = (
                        self._command(
                            ["merge-base", old["head"], request["head"]],
                            65536,
                            allow_failure=True,
                        )
                        .decode()
                        .strip()
                    )
                    return None, "append" if base == old["head"] else "rewrite"
                return None, "bounded_rebuild"
        return None, "cold"

    def _new_view(self, request: dict[str, Any]) -> str:
        self.traversals += 1
        cap = min(67108864, 65536 + (self.options.max_commits + 1) * 66)
        view_id = uuid4().hex
        selection = {
            "count": 0,
            "ids_sha256": hashlib.sha256().hexdigest(),
            "history_truncated": False,
        }
        raw = _bytes(selection).decode()
        with self.db:
            self.db.execute(
                "INSERT INTO views VALUES(?,?,?,?,?,?,?)",
                (
                    view_id,
                    _bytes(request).decode(),
                    raw,
                    _digest(raw.encode()),
                    "selecting",
                    None,
                    None,
                ),
            )
        h = hashlib.sha256()
        count = 0
        truncated = False
        # The Git traversal is drained into a finite disk spool, then SHA lines
        # are accepted in bounded batches. No complete ID/metadata list is built.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            if request["head"] is not None:
                outcome = run_bounded_process(
                    [
                        self.executable,
                        *self.read_only_options,
                        "rev-list",
                        f"--max-count={self.options.max_commits+1}",
                        request["head"],
                    ],
                    cwd=self.cwd,
                    stdout=stdout,
                    stderr=stderr,
                    timeout_seconds=self.options.timeout_seconds,
                    limits=ProcessLimits(
                        max_log_bytes=cap, termination_grace_seconds=0.2
                    ),
                    environment=self.environment,
                )
                if (
                    outcome.status != "passed"
                    or outcome.stdout_bytes + outcome.stderr_bytes
                    > outcome.captured_bytes
                ):
                    raise IntegrityError(
                        "Git revision traversal failed/timed out or exceeded its bounded spool"
                    )
            stdout.seek(0)
            batch = []
            while line := stdout.readline(128):
                sha = line.strip().decode("ascii")
                if not _SHA.fullmatch(sha):
                    raise IntegrityError("Invalid Git revision stream identity")
                if count == self.options.max_commits:
                    truncated = True
                    break
                h.update((sha + "\n").encode())
                batch.append((view_id, count, sha))
                count += 1
                if len(batch) == 256:
                    with self.db:
                        self.db.executemany(
                            "INSERT INTO view_records(view_id,ordinal,commit_id) VALUES(?,?,?)",
                            batch,
                        )
                    batch.clear()
            if batch:
                with self.db:
                    self.db.executemany(
                        "INSERT INTO view_records(view_id,ordinal,commit_id) VALUES(?,?,?)",
                        batch,
                    )
        selection = {
            "count": count,
            "ids_sha256": h.hexdigest(),
            "history_truncated": truncated,
        }
        raw = _bytes(selection).decode()
        with self.db:
            self.db.execute(
                "UPDATE views SET selection=?,selection_sha=?,state='building' WHERE id=?",
                (raw, _digest(raw.encode()), view_id),
            )
        return view_id

    def _load(
        self, sha: str, expected: str | None = None
    ) -> tuple[dict[str, Any] | None, bool]:
        row = self.db.execute(
            "SELECT payload,sha256 FROM raw_records WHERE profile=? AND commit_id=?",
            (self.profile_id, sha),
        ).fetchone()
        if row is None:
            return None, expected is not None
        try:
            if (
                len(row[0]) > self.options.max_record_bytes
                or _digest(row[0]) != row[1]
                or (expected is not None and expected != row[1])
            ):
                raise IntegrityError("Raw record hash mismatch")
            record = json.loads(row[0])
            validate_raw_record(record)
            if record["commit_id"] != sha:
                raise IntegrityError("Raw record subject mismatch")
            return record, False
        except (
            IntegrityError,
            ContractError,
            ValueError,
            TypeError,
            KeyError,
            UnicodeError,
        ):
            return None, True

    def _extract(self, sha: str) -> dict[str, Any]:
        record = {
            "version": "1.0.0",
            "commit_id": sha,
            "parents": [],
            "author": {"name": "unknown", "email": ""},
            "committed_date": 0,
            "message": "",
            "changes": [],
            "total_files": 0,
            "available": False,
            "limitations": [],
        }
        try:
            commit = self.repo.commit(sha)
            if self.repo.odb.info(commit.binsha).size > self.options.max_record_bytes:
                raise IntegrityError("Commit metadata exceeds max_record_bytes")
            record.update(
                parents=[p.hexsha for p in commit.parents],
                author={
                    "name": commit.author.name or "",
                    "email": commit.author.email or "",
                },
                committed_date=commit.committed_date,
                message=commit.message,
            )
            args = [
                "--attr-source=" + sha,
                "diff-tree",
                "--no-commit-id",
                "--root",
                "--no-ext-diff",
                "--no-textconv",
                "--raw",
                "--numstat",
                "-z",
                "-r",
                "-M50%",
            ]
            args.extend([record["parents"][0], sha] if record["parents"] else [sha])
            changes = _parse_delta(self._command(args, self.options.max_record_bytes))
            record.update(changes=changes, total_files=len(changes), available=True)
            if len(_bytes(record)) > self.options.max_record_bytes:
                raise IntegrityError("Encoded raw record exceeds max_record_bytes")
            validate_raw_record(record)
        except (
            git.GitError,
            OSError,
            ValueError,
            UnicodeError,
            ContractError,
        ) as error:
            record.update(
                changes=[],
                total_files=0,
                available=False,
                limitations=[
                    f"History delta unavailable for {sha[:8]}: {type(error).__name__}: {str(error)[:300]}"
                ],
            )
        return record

    def _accept(
        self, view_id: str, ordinal: int, sha: str, record: dict[str, Any]
    ) -> str:
        validate_raw_record(record)
        raw = _bytes(record)
        if len(raw) > self.options.max_record_bytes:
            raise IntegrityError("Raw record exceeds accepted byte bound")
        digest = _digest(raw)
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO raw_records VALUES(?,?,?,?)",
                (self.profile_id, sha, raw, digest),
            )
            self.db.execute(
                "UPDATE view_records SET record_sha=? WHERE view_id=? AND ordinal=?",
                (digest, view_id, ordinal),
            )
        _accepted_checkpoint(sha)
        return digest

    def _checked_record(self, sha: str, digest: str) -> dict[str, Any]:
        record, bad = self._load(sha, digest)
        if bad or record is None:
            raise IntegrityError("Accepted raw Git record changed or disappeared")
        return record

    def records(self, view_id: str) -> Iterator[dict[str, Any]]:
        """Iterate checked accepted raw records without a full history list."""
        for sha, digest in self.db.execute(
            "SELECT commit_id,record_sha FROM view_records WHERE view_id=? ORDER BY ordinal",
            (view_id,),
        ):
            if digest is None:
                raise IntegrityError(
                    "Pending history record cannot be read as accepted"
                )
            yield self._checked_record(sha, digest)

    def _complete_view(
        self, view_id: str, request: dict[str, Any], selection: dict[str, Any]
    ) -> dict[str, Any]:
        facts = hashlib.sha256()
        notes = []
        complete = True
        if self.shallow != "full":
            notes.append(
                "Shallow history: earlier changes and contributors are unavailable."
            )
        if selection["history_truncated"]:
            notes.append(
                f"History traversal truncated at configured max_commits={self.options.max_commits}; earlier changes are unavailable."
            )
        for ordinal, sha, expected in self.db.execute(
            "SELECT ordinal,commit_id,record_sha FROM view_records WHERE view_id=? ORDER BY ordinal",
            (view_id,),
        ):
            record, bad = self._load(sha, expected)
            if record is not None and record["available"]:
                self.reused += 1
                digest = _digest(_bytes(record))
                if expected is None:
                    with self.db:
                        self.db.execute(
                            "UPDATE view_records SET record_sha=? WHERE view_id=? AND ordinal=?",
                            (digest, view_id, ordinal),
                        )
            else:
                self.recovered += int(bad)
                record = self._extract(sha)
                self.extracted += 1
                digest = self._accept(view_id, ordinal, sha, record)
            facts.update((sha + ":" + digest + "\n").encode())
            notes.extend(record["limitations"])
            complete &= record["available"]
            if len(record["parents"]) > 1:
                notes.append(
                    "Merge history uses first-parent deltas; cross-branch rename lineage is not verified."
                )
        descriptor = {
            "version": "1.0.0",
            "request": request,
            "selection": selection,
            "facts_sha256": facts.hexdigest(),
            "complete": complete,
            "limitations": list(dict.fromkeys(notes)),
        }
        validate_history_document("checkpoint", descriptor)
        encoded = _bytes(descriptor).decode()
        with self.db:
            self.db.execute(
                "UPDATE views SET state=?,descriptor=?,descriptor_sha=? WHERE id=?",
                ("ready", encoded, _digest(encoded.encode()), view_id),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES('current_view',?)", (view_id,)
            )
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES('last_profile',?)",
                (_bytes(self.profile).decode(),),
            )
        return descriptor

    def _project(
        self, view_id: str, files: set[str], notes: list[str]
    ) -> tuple[str, list[str]]:
        file_digest = digest_json(sorted(files))
        view_hash = self.db.execute(
            "SELECT descriptor_sha FROM views WHERE id=?", (view_id,)
        ).fetchone()[0]
        projection_id = digest_json(
            {
                "view": view_id,
                "files": file_digest,
                "facts": view_hash,
                "notes": digest_json(notes),
            }
        )
        existing = self.db.execute(
            "SELECT descriptor,descriptor_sha FROM projections WHERE id=?",
            (projection_id,),
        ).fetchone()
        if existing is not None:
            try:
                if _digest(existing[0].encode()) != existing[1]:
                    raise IntegrityError("Projection descriptor changed")
                expected = json.loads(existing[0])
                observed_hash = hashlib.sha256()
                observed_count = 0
                for ordinal, raw, digest in self.db.execute(
                    "SELECT ordinal,payload,sha256 FROM projected_changes WHERE projection_id=? ORDER BY ordinal",
                    (projection_id,),
                ):
                    if ordinal != observed_count or _digest(raw) != digest:
                        raise IntegrityError("Projection row changed")
                    observed_hash.update((digest + "\n").encode())
                    observed_count += 1
                if (
                    observed_count != expected["count"]
                    or observed_hash.hexdigest() != expected["rows_sha256"]
                    or expected["files_digest"] != file_digest
                    or expected["view_id"] != view_id
                ):
                    raise IntegrityError("Projection inventory changed")
                return projection_id, expected["limitations"]
            except (IntegrityError, ValueError, KeyError, TypeError):
                pass
        # Projections are disposable and rebuilt once per scan from accepted raw
        # facts. Every consumer then shares this checked disk stream.
        aliases = {path: path for path in files}
        ordinal = 0
        h = hashlib.sha256()
        limitations = list(notes)
        with self.db:
            self.db.execute(
                "DELETE FROM projected_changes WHERE projection_id=?", (projection_id,)
            )
            self.db.execute("DELETE FROM projections WHERE id=?", (projection_id,))
        for record in self.records(view_id):
            updates = []
            destinations = [
                (row, aliases.get(row["new_path"])) for row in record["changes"]
            ]
            with self.db:
                for row, current in destinations:
                    if current is None:
                        continue
                    payload = {
                        "file": current,
                        "parent_file": row["old_path"],
                        "commit_id": record["commit_id"],
                        "insertions": row["insertions"],
                        "deletions": row["deletions"],
                    }
                    raw = _bytes(payload)
                    digest = _digest(raw)
                    h.update((digest + "\n").encode())
                    self.db.execute(
                        "INSERT INTO projected_changes VALUES(?,?,?,?)",
                        (projection_id, ordinal, raw, digest),
                    )
                    ordinal += 1
                    if row["binary"]:
                        limitations.append(
                            f"Binary history statistics unavailable for {current}."
                        )
                    if row["status"] in {"A", "R", "C"}:
                        updates.append(
                            (
                                row["new_path"],
                                row["old_path"] if row["status"] == "R" else None,
                                current,
                            )
                        )
            for destination, _, _ in updates:
                aliases.pop(destination, None)
            for _, original, current in updates:
                if original is not None:
                    aliases[original] = current
        descriptor = {
            "view_id": view_id,
            "files_digest": file_digest,
            "rows_sha256": h.hexdigest(),
            "count": ordinal,
            "limitations": list(dict.fromkeys(limitations)),
        }
        raw = _bytes(descriptor).decode()
        with self.db:
            self.db.execute(
                "INSERT INTO projections VALUES(?,?,?,?)",
                (projection_id, view_id, raw, _digest(raw.encode())),
            )
        return projection_id, descriptor["limitations"]

    def open_scan(
        self, files: set[str], initial_notes: list[str], *, revision: str | None = None
    ):
        """Accept/recover raw facts, then expose one checked shared projection."""
        from .history import HistoryScan

        if revision is not None:
            if not isinstance(revision, str) or not _SHA.fullmatch(revision):
                raise ContractError(
                    "History revision must be an explicit full commit ID"
                )
            try:
                head = self.repo.commit(revision).hexsha
            except (ValueError, git.GitError) as error:
                raise ContractError(
                    "Selected history revision is unavailable"
                ) from error
        else:
            try:
                head = self.repo.head.commit.hexsha
            except (ValueError, git.GitError):
                head = None
        request = self._request(head)
        view_id, mode = self._existing(request)
        if view_id is None:
            view_id = self._new_view(request)
        selection = self._selection(view_id)
        descriptor = self._complete_view(view_id, request, selection)
        projection, notes = self._project(
            view_id, files, [*initial_notes, *descriptor["limitations"]]
        )
        if head is None:
            notes.append("Repository has no readable commit history.")
        info = {
            "version": "1.0.0",
            "method": PROFILE,
            "mode": mode,
            "head": head,
            "profile_digest": self.profile_id,
            "checkpoint_sha256": digest_json(descriptor),
            "selection": selection,
            "records_extracted": self.extracted,
            "records_reused": self.reused,
            "recovered_records": self.recovered,
            "revision_traversals": self.traversals,
            "history_truncated": selection["history_truncated"],
            "selected_records_complete": descriptor["complete"],
            "current_files_digest": digest_json(sorted(files)),
            "bounds": {
                key: value
                for key, value in asdict(self.options).items()
                if key != "cache_dir"
            },
            "limitations": [
                *notes,
                "Raw Git cache is derived local state, not authenticated producer or current execution evidence.",
                "SQLite database pages are byte-capped; transient rollback journal and per-command bounded capture add temporary disk overhead.",
            ],
        }
        unchanged = False
        try:
            with Path(self.executable).open("rb") as binary:
                observed_binary = hashlib.file_digest(binary, "sha256").hexdigest()
            unchanged = (
                self._shallow() == self.shallow
                and not (Path(self.repo.common_dir) / "info/grafts").exists()
                and self._attribute_identity() == self.attributes
                and self._source_materials() == self.source_materials
                and observed_binary == self.profile["git_executable_sha256"]
            )
        except (OSError, IntegrityError):
            pass
        if not unchanged:
            # Discard derived raw hits from an interrupted input generation;
            # prior immutable user reports are not modified or relabelled.
            with self.db:
                self.db.execute(
                    "DELETE FROM raw_records WHERE profile=?", (self.profile_id,)
                )
            raise IntegrityError(
                "Git boundary, attributes, executable or producer changed during collection"
            )
        if self.path.stat().st_size > self.options.max_cache_bytes:
            raise IntegrityError(
                "History cache exceeded requested actual file byte budget"
            )
        validate_history_document("result", info)
        return HistoryScan(
            files=files,
            commits=CommitSequence(self, view_id, selection["count"]),
            changes=ChangeSequence(self, view_id, projection),
            limitations=list(dict.fromkeys(notes)),
            commit_file_counts=FileCountMapping(self, view_id, selection["count"]),
            cache_info=info,
            _cache_owner=self,
        )


class CommitSequence(Sequence[StoredCommit]):
    """Compatibility sequence backed by checked disk records, not a full list."""

    def __init__(self, owner: HistoryDatabase, view_id: str, count: int):
        self.owner = owner
        self.view_id = view_id
        self.count = count

    def __len__(self) -> int:
        return self.count

    def __iter__(self) -> Iterator[StoredCommit]:
        for record in self.owner.records(self.view_id):
            yield _commit(record)

    def __getitem__(self, index):
        if isinstance(index, slice):
            start, stop, step = index.indices(self.count)
            return [self[i] for i in range(start, stop, step)]
        if index < 0:
            index += self.count
        row = self.owner.db.execute(
            "SELECT commit_id,record_sha FROM view_records WHERE view_id=? AND ordinal=?",
            (self.view_id, index),
        ).fetchone()
        if row is None:
            raise IndexError(index)
        return _commit(self.owner._checked_record(row[0], row[1]))


class FileCountMapping(Mapping[str, int]):
    """Shared all-path touched counts for bulk filtering without another diff."""

    def __init__(self, owner: HistoryDatabase, view_id: str, count: int):
        self.owner = owner
        self.view_id = view_id
        self.count = count

    def __len__(self) -> int:
        return self.count

    def __iter__(self) -> Iterator[str]:
        for row in self.owner.db.execute(
            "SELECT commit_id FROM view_records WHERE view_id=? ORDER BY ordinal",
            (self.view_id,),
        ):
            yield row[0]

    def __getitem__(self, key: str) -> int:
        row = self.owner.db.execute(
            "SELECT record_sha FROM view_records WHERE view_id=? AND commit_id=?",
            (self.view_id, key),
        ).fetchone()
        if row is None:
            raise KeyError(key)
        return self.owner._checked_record(key, row[0])["total_files"]


class ChangeSequence(Iterable):
    """Shared projected changes; validates every retained row and stream total."""

    def __init__(self, owner: HistoryDatabase, view_id: str, projection_id: str):
        self.owner = owner
        self.view_id = view_id
        self.projection_id = projection_id

    def __iter__(self):
        from .history import HistoryChange

        header = self.owner.db.execute(
            "SELECT descriptor,descriptor_sha FROM projections WHERE id=?",
            (self.projection_id,),
        ).fetchone()
        if header is None or _digest(header[0].encode()) != header[1]:
            raise IntegrityError("Projected history checkpoint changed")
        descriptor = json.loads(header[0])
        h = hashlib.sha256()
        count = 0
        last_sha = None
        commit = None
        for ordinal, raw, digest in self.owner.db.execute(
            "SELECT ordinal,payload,sha256 FROM projected_changes WHERE projection_id=? ORDER BY ordinal",
            (self.projection_id,),
        ):
            if ordinal != count or _digest(raw) != digest:
                raise IntegrityError("Projected history row integrity mismatch")
            row = json.loads(raw)
            h.update((digest + "\n").encode())
            count += 1
            if row["commit_id"] != last_sha:
                expected = self.owner.db.execute(
                    "SELECT record_sha FROM view_records WHERE view_id=? AND commit_id=?",
                    (self.view_id, row["commit_id"]),
                ).fetchone()
                if expected is None:
                    raise IntegrityError("Projection refers to an unaccepted commit")
                commit = _commit(
                    self.owner._checked_record(row["commit_id"], expected[0])
                )
                last_sha = row["commit_id"]
            yield HistoryChange(
                row["file"],
                row["parent_file"],
                commit,
                row["insertions"],
                row["deletions"],
            )
        if count != descriptor["count"] or h.hexdigest() != descriptor["rows_sha256"]:
            raise IntegrityError("Projected history stream cardinality/hash mismatch")
