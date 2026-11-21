"""Transactional, selected-artifact SQLite query caches; never analysis reuse.

Only the committed derived run is a RunSnapshot. Original source access is a
strictly narrower metadata/selected-file projection, not a verified full run.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import time
from typing import Any
from uuid import uuid4

import jsonschema

from cppulse.contracts import load_schema, validate
from cppulse.contracts.frozen_input import _EXACT_INTEGER_VALIDATOR
from cppulse.contracts.json_stream import JsonStreamLimits, VERSION as STREAM_VERSION
from cppulse.contracts.result_index import validate_index_request
from cppulse.errors import ContractError, IntegrityError
from cppulse.identities import canonical_json_bytes
from cppulse.store_coordination import publication_guard
from cppulse.store_heads import protocol
from cppulse.json_stream import iter_json_array
from cppulse.run_store import (
    RunStore,
    _directory,
    _read,
    _relative,
    _run_id,
    _NO_SOURCE_CHECK,
)

VERSION = "0.1.0"
_DEFAULTS = dict(
    max_index_bytes=256 * 1024**2,
    max_rows=1_000_000,
    max_item_bytes=1024**2,
    sqlite_cache_kib=8192,
    wall_seconds=300,
)
_LIMITATIONS = [
    "Selected original artifact only; other artifacts and ignored metadata semantics are unverified.",
    "Derived query optimization only; no native execution, original source verification or analysis cache eligibility.",
]
_META_LIMIT = 64 * 1024**2
_RECEIPT_LIMIT = 64 * 1024
_TABLE_SQL = "CREATE TABLE findings (ordinal INTEGER PRIMARY KEY, category TEXT NOT NULL, file TEXT NOT NULL, message TEXT NOT NULL, raw BLOB NOT NULL)"
_INDEX_SQL = {
    "findings_category": "CREATE INDEX findings_category ON findings(category)",
    "findings_file": "CREATE INDEX findings_file ON findings(file)",
}
_VERSIONS = {
    "operation": "derived-result-index",
    "index": VERSION,
    "stream": STREAM_VERSION,
    "native_executed": "false",
    "analysis_cache_eligible": "false",
}


def _json(raw: bytes) -> Any:
    def constant(value: str) -> None:
        raise ValueError("Nonfinite JSON literal: " + value)

    def floating(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Nonfinite JSON number")
        return number

    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            parse_constant=constant,
            parse_float=floating,
            object_pairs_hook=pairs,
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ContractError("Invalid finite JSON index material") from error


def _store(source_store: RunStore | str | Path) -> RunStore:
    return (
        source_store
        if isinstance(source_store, RunStore)
        else RunStore.open_existing(source_store)
    )


def _deadline(seconds: int):
    end = time.monotonic() + seconds

    def check():
        if time.monotonic() > end:
            raise ContractError("Result index wall-time budget exceeded")

    return check


def _identity(value):
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


class _Pinned:
    def __init__(self, path: Path, size: int, digest: str, check):
        self.path, self.size, self.digest, self.check_time = path, size, digest, check
        self.parent = _directory(path.parent)
        parent = self.parent.__enter__()
        self.parent_start = os.fstat(parent)
        try:
            fd = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
            self.stream = os.fdopen(fd, "rb", buffering=0)
            self.start = os.fstat(fd)
            if not stat.S_ISREG(self.start.st_mode) or self.start.st_size != size:
                raise IntegrityError(
                    "Selected result material is not the pinned regular file"
                )
            self.guard()
        except BaseException as error:
            if hasattr(self, "stream"):
                self.stream.close()
            self.parent.__exit__(None, None, None)
            if isinstance(error, OSError):
                raise IntegrityError(
                    "Selected result material cannot be opened safely"
                ) from error
            raise

    def guard(self):
        self.check_time()
        try:
            with _directory(self.path.parent) as parent:
                if (os.fstat(parent).st_dev, os.fstat(parent).st_ino) != (
                    self.parent_start.st_dev,
                    self.parent_start.st_ino,
                ):
                    raise IntegrityError("Selected result parent directory changed")
                now = os.stat(self.path.name, dir_fd=parent, follow_symlinks=False)
            if _identity(now) != _identity(self.start) or _identity(
                os.fstat(self.stream.fileno())
            ) != _identity(self.start):
                raise IntegrityError("Selected result material identity changed")
        except OSError as error:
            raise IntegrityError("Selected result material path changed") from error

    def verify(self):
        self.guard()
        self.stream.seek(0)
        digest = hashlib.sha256()
        size = 0
        while block := self.stream.read(min(64 * 1024, self.size - size + 1)):
            self.check_time()
            size += len(block)
            if size > self.size:
                raise IntegrityError("Selected material grew during verification")
            digest.update(block)
        self.guard()
        if size != self.size or digest.hexdigest() != self.digest:
            raise IntegrityError("Selected result material SHA/size changed")
        self.stream.seek(0)

    def read(self, size):
        self.check_time()
        return self.stream.read(size)

    def close(self):
        self.stream.close()
        self.parent.__exit__(None, None, None)


def _metadata(store, run_id, digest):
    original_protocol = protocol(store.root)
    path = store.root / "runs" / _run_id(run_id) / "run_manifest.json"
    raw = _read(path, max_bytes=_META_LIMIT)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise IntegrityError("Original manifest SHA differs from pin")
    document = _json(raw)
    validate("run_manifest", document)
    if document["run_id"] != run_id:
        raise IntegrityError("Original manifest run ID differs from selection")
    if protocol(store.root) != original_protocol:
        raise IntegrityError("Original store protocol changed during metadata read")
    return path, raw, document


def read_source_manifest_metadata(source_store, run_id, manifest_sha256) -> dict:
    """Read only bounded pinned manifest metadata; never verify artifact payloads.

    This detached document is not a RunSnapshot or source-verification receipt.
    The recorded input_verification is an original manifest claim, not a check
    performed by this function.
    """
    return deepcopy(_metadata(_store(source_store), run_id, manifest_sha256)[2])


def make_index_request(
    source_store, run_id, manifest_sha256, artifact_id, *, limits=None
) -> dict:
    """Pin metadata and exactly one descriptor without opening other artifacts."""
    store = _store(source_store)
    _, _, manifest = _metadata(store, run_id, manifest_sha256)
    matches = [row for row in manifest["artifacts"] if row["id"] == artifact_id]
    if len(matches) != 1:
        raise IntegrityError("Selected result artifact ID is absent or ambiguous")
    row = matches[0]
    if row.get("contract") not in (
        None,
        {"kind": "findings", "version": "prototype_v1"},
    ):
        raise ContractError(
            "Selected result artifact declares an unsupported report dialect"
        )
    request = {
        "version": VERSION,
        "kind": "prototype_findings",
        "read_scope": "selected_artifact_only",
        "source": {
            "run_id": run_id,
            "manifest_sha256": manifest_sha256,
            "artifact_id": artifact_id,
            "artifact_path": _relative(row["path"]),
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
        },
        "limits": deepcopy(_DEFAULTS if limits is None else limits),
    }
    validate_index_request(request)
    return request


@contextmanager
def _selected(store, request, check):
    pin = request["source"]
    original_protocol = protocol(store.root)
    path, raw, manifest = _metadata(store, pin["run_id"], pin["manifest_sha256"])
    expected = make_index_request(
        store,
        pin["run_id"],
        pin["manifest_sha256"],
        pin["artifact_id"],
        limits=request["limits"],
    )
    if expected != request:
        raise IntegrityError("Selected original descriptor differs from request")
    held = []
    try:
        mf = _Pinned(path, len(raw), pin["manifest_sha256"], check)
        held.append(mf)
        artifact = _Pinned(
            path.parent / _relative(pin["artifact_path"]),
            pin["size_bytes"],
            pin["sha256"],
            check,
        )
        held.append(artifact)

        def guard(*, identity_only=False):
            if protocol(store.root) != original_protocol:
                raise IntegrityError(
                    "Original store protocol changed during selected read"
                )
            if not identity_only:
                mf.verify()
                artifact.verify()
            mf.guard()
            artifact.guard()
            if protocol(store.root) != original_protocol:
                raise IntegrityError(
                    "Original store protocol changed during selected read"
                )

        yield manifest, artifact, guard
    finally:
        for item in reversed(held):
            item.close()


def _digest(request):
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "request": request,
                "index_version": VERSION,
                "stream_version": STREAM_VERSION,
            }
        )
    ).hexdigest()


def _cache_path(store, cache_root, request):
    path = Path(cache_root).absolute()
    original = store.root
    if path == original or any(
        path.is_relative_to(original / name)
        for name in ("runs", ".staging", ".recovery")
    ):
        raise ContractError(
            "Query cache must be separate from original store authority"
        )
    # Resolve every existing ancestor without following links before creation.
    with _directory(path, create=True):
        pass
    return path / _digest(request)


def _connect(path, limits, check, *, readonly=False):
    connection = sqlite3.connect(
        "file:" + str(path) + "?mode=ro&immutable=1" if readonly else str(path),
        uri=readonly,
        timeout=0,
    )
    connection.enable_load_extension(False)
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.execute("PRAGMA cache_size=-" + str(limits["sqlite_cache_kib"]))
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.set_progress_handler(lambda: _progress(check), 1000)
    if readonly:
        connection.execute("PRAGMA query_only=ON")
    else:
        connection.execute("PRAGMA page_size=4096")
        connection.execute(
            "PRAGMA max_page_count=" + str(limits["max_index_bytes"] // 4096)
        )
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
    return connection


def _progress(check):
    try:
        check()
    except ContractError:
        return 1
    return 0


def _write_new(path, raw, *, parent_fd=None):
    with (
        _directory(path.parent) if parent_fd is None else nullcontext(parent_fd)
    ) as parent:
        fd = os.open(
            path.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


def _cache_protocol(snapshot):
    if protocol(snapshot._root) is None:
        raise IntegrityError(
            "Derived index cache requires its active v3 store protocol"
        )


def _check_cache_manifest(manifest, request, *, original_source=None):
    entries = manifest["artifacts"]
    if (
        len(entries) != 2
        or {row["id"] for row in entries} != {"index", "receipt"}
        or any("contract" in row for row in entries)
        or any(
            (row["path"], row["media_type"])
            != (
                ("index.sqlite" if row["id"] == "index" else "receipt.json"),
                "application/octet-stream",
            )
            for row in entries
        )
    ):
        raise IntegrityError("Derived index must retain exactly two opaque artifacts")
    by_id = {row["id"]: row for row in entries}
    if any(
        type(row["size_bytes"]) is not int  # noqa: E721 -- exact descriptor bytes
        or row["size_bytes"] < 0
        for row in entries
    ):
        raise IntegrityError("Derived index descriptor sizes must be exact integers")
    if (
        by_id["index"]["size_bytes"] > request["limits"]["max_index_bytes"]
        or by_id["receipt"]["size_bytes"] > _RECEIPT_LIMIT
    ):
        raise IntegrityError("Derived index artifact exceeds declared budgets")
    if (
        manifest["status"] != "completed"
        or manifest.get("input_verification") != "unverified"
        or manifest["versions"] != _VERSIONS
        or manifest["contexts"] != []
        or manifest["stages"] != []
        or manifest["limitations"] != _LIMITATIONS + [_NO_SOURCE_CHECK]
        or (original_source is not None and manifest["source"] != original_source)
        or manifest["config_digest"] != _digest(request)
    ):
        raise IntegrityError("Derived index manifest scope differs from request")


def _cache_preflight(
    cache, run_id, manifest_sha256, request, check, *, original_source=None
):
    """Check bounded private metadata and physical sizes BEFORE payload reads."""
    selected_protocol = protocol(cache.root)
    if selected_protocol is None:
        raise IntegrityError(
            "Derived index cache requires its active v3 store protocol"
        )
    manifest_path, raw, manifest = _metadata(cache, run_id, manifest_sha256)
    _check_cache_manifest(manifest, request, original_source=original_source)
    for entry in manifest["artifacts"]:
        held = _Pinned(
            manifest_path.parent / _relative(entry["path"]),
            entry["size_bytes"],
            entry["sha256"],
            check,
        )
        held.close()  # metadata-only: factory verification still reads/checks bytes
    if protocol(cache.root) != selected_protocol:
        raise IntegrityError("Derived index store protocol changed during preflight")
    return len(raw) + sum(entry["size_bytes"] for entry in manifest["artifacts"])


def _open_cached(cache, reference, request, check, *, original_source):
    budget = _cache_preflight(
        cache,
        reference["run_id"],
        reference["manifest_sha256"],
        request,
        check,
        original_source=original_source,
    )
    return cache.open_run(
        reference["run_id"],
        manifest_sha256=reference["manifest_sha256"],
        max_snapshot_bytes=budget,
    )


def _receipt(snapshot, request, *, original_source=None, check=None):
    _cache_protocol(snapshot)
    _cache_preflight(
        RunStore.open_existing(snapshot._root),
        snapshot.run_id,
        snapshot.manifest_sha256,
        request,
        _deadline(request["limits"]["wall_seconds"]) if check is None else check,
        original_source=original_source,
    )
    _check_cache_manifest(snapshot.manifest, request, original_source=original_source)
    snapshot.verify()
    receipt = _json(snapshot.read_bytes("receipt"))
    if (
        not isinstance(receipt, dict)
        or receipt.get("request") != request
        or receipt.get("index_version") != VERSION
        or receipt.get("stream_version") != STREAM_VERSION
        or set(receipt)
        != {
            "version",
            "index_version",
            "stream_version",
            "request",
            "complete",
            "rows",
            "native_executed",
            "analysis_cache_eligible",
            "read_scope",
            "limitations",
        }
        or receipt.get("version") != VERSION
        or receipt.get("native_executed") is not False
        or receipt.get("analysis_cache_eligible") is not False
        or receipt.get("read_scope") != "selected_artifact_only"
        or receipt.get("limitations") != _LIMITATIONS
        or receipt.get("complete") is not True
        or type(receipt.get("rows")) is not int  # noqa: E721 -- exact count
        or not 0 <= receipt["rows"] <= request["limits"]["max_rows"]
    ):
        raise IntegrityError(
            "Derived result receipt differs from request/version/completeness pins"
        )
    return receipt


def _finding_validator():
    return _EXACT_INTEGER_VALIDATOR(
        load_schema("findings", "prototype_v1")["properties"]["findings"]["items"]
    )


def _finding(raw, validator):
    if type(raw) is not bytes:  # noqa: E721 -- opaque BLOB profile
        raise IntegrityError("Result index row must retain raw JSON bytes")
    document = _json(raw)
    # A forged but hash-consistent private cache still cannot introduce invalid
    # Unicode that the original streaming producer would have rejected.
    pending = [document]
    try:
        while pending:
            value = pending.pop()
            if isinstance(value, str):
                value.encode("utf-8", errors="strict")
            elif isinstance(value, dict):
                pending.extend(value.keys())
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        validator.validate(document)
    except (UnicodeError, jsonschema.ValidationError, RecursionError) as error:
        raise ContractError(
            "Selected finding item violates prototype_v1 schema or Unicode"
        ) from error
    return document


def _database_profile(connection, rows):
    expected = [
        ("index", name, "findings", sql) for name, sql in _INDEX_SQL.items()
    ] + [("table", "findings", "findings", _TABLE_SQL)]
    actual = connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name LIMIT 4"
    ).fetchmany(4)
    if actual != sorted(expected):
        raise IntegrityError("Unsupported result index SQLite schema/DDL profile")
    columns = connection.execute("PRAGMA table_xinfo(findings)").fetchmany(6)
    wanted = [(0, "ordinal", "INTEGER", 0, None, 1, 0)] + [
        (i, name, kind, 1, None, 0, 0)
        for i, (name, kind) in enumerate(
            [
                ("category", "TEXT"),
                ("file", "TEXT"),
                ("message", "TEXT"),
                ("raw", "BLOB"),
            ],
            1,
        )
    ]
    if columns != wanted:
        raise IntegrityError("Unsupported result index column profile")
    for name, column, ordinal in [
        ("findings_category", "category", 1),
        ("findings_file", "file", 2),
    ]:
        if connection.execute("PRAGMA index_info(" + name + ")").fetchmany(2) != [
            (0, ordinal, column)
        ]:
            raise IntegrityError("Unsupported result index key profile")
    for name, expected_value in [
        ("application_id", 0),
        ("user_version", 0),
        ("page_size", 4096),
        ("encoding", "UTF-8"),
    ]:
        if connection.execute("PRAGMA " + name).fetchone()[0] != expected_value:
            raise IntegrityError("Unsupported result index SQLite metadata")
    count, first, last = connection.execute(
        "SELECT count(*), min(ordinal), max(ordinal) FROM findings"
    ).fetchone()
    if (count, first, last) != (rows, 0 if rows else None, rows - 1 if rows else None):
        raise IntegrityError("Index occurrence ordinals differ from retained receipt")


def _verify_database(snapshot, request, receipt, check):
    entry = snapshot._entry("index")
    database = _Pinned(
        snapshot.path / _relative(entry["path"]),
        entry["size_bytes"],
        entry["sha256"],
        check,
    )
    connection = None
    try:
        database.verify()
        connection = _connect(
            Path("/proc/self/fd") / str(database.stream.fileno()),
            request["limits"],
            check,
            readonly=True,
        )
        _database_profile(connection, receipt["rows"])
        database.verify()
        snapshot._check_manifest()
        _cache_protocol(snapshot)
    except sqlite3.Error as error:
        raise IntegrityError(
            "Result index SQLite schema verification failed"
        ) from error
    finally:
        if connection is not None:
            connection.close()
        database.close()


class ResultIndex:
    """Verified derived snapshot with selected-original guarded page queries."""

    def __init__(self, store, snapshot, request, reused):
        self._source_store, self.snapshot, self._request, self.reused = (
            store,
            snapshot,
            deepcopy(request),
            reused,
        )

    @property
    def request(self):
        """Return a detached request, never mutable internal identity state."""
        return deepcopy(self._request)

    def page(
        self,
        *,
        page=1,
        per_page=50,
        category=None,
        file=None,
        text=None,
        max_page_bytes=4 * 1024**2,
    ) -> dict:
        """Return one bounded page only after source and cache revalidation."""
        for name, value, bound in [
            ("page", page, 2**63 - 1),
            ("per_page", per_page, 200),
            ("max_page_bytes", max_page_bytes, 32 * 1024**2),
        ]:
            if (
                type(value) is not int  # noqa: E721 -- exact finite budget
                or not 1 <= value <= bound
            ):
                raise ContractError("Invalid result page budget: " + name)
        for value in (category, file, text):
            if value is not None and (
                not isinstance(value, str) or len(value) > 4096 or "\x00" in value
            ):
                raise ContractError("Invalid bounded result filter")
            if value is not None:
                try:
                    if len(value.encode("utf-8")) > 4096:
                        raise ContractError("Result filter UTF8 budget exceeded")
                except UnicodeError as error:
                    raise ContractError("Invalid result filter Unicode") from error
        request = self._request
        check = _deadline(request["limits"]["wall_seconds"])
        with _selected(self._source_store, request, check) as (
            original_manifest,
            _,
            guard,
        ):
            guard()
            receipt = _receipt(
                self.snapshot,
                request,
                original_source=original_manifest["source"],
                check=check,
            )
            entry = self.snapshot._entry("index")
            database = _Pinned(
                self.snapshot.path / _relative(entry["path"]),
                entry["size_bytes"],
                entry["sha256"],
                check,
            )
            connection = None
            try:
                database.verify()
                connection = _connect(
                    Path("/proc/self/fd") / str(database.stream.fileno()),
                    request["limits"],
                    check,
                    readonly=True,
                )
                _database_profile(connection, receipt["rows"])
                validator = _finding_validator()
                clauses = []
                params = []
                for column, value in [("category", category), ("file", file)]:
                    if value is not None:
                        clauses.append(column + " = ?")
                        params.append(value)
                if text is not None:
                    clauses.append("instr(message, ?) > 0")
                    params.append(text)
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                total = connection.execute(
                    "SELECT count(*) FROM findings" + where, params
                ).fetchone()[0]
                if (
                    connection.execute("SELECT count(*) FROM findings").fetchone()[0]
                    != receipt["rows"]
                ):
                    raise IntegrityError(
                        "Index row count differs from retained receipt"
                    )
                if (page - 1) * per_page > 2**63 - 1:
                    raise ContractError(
                        "Result page offset exceeds SQLite finite range"
                    )
                items = []
                used = 0
                cap = request["limits"]["max_item_bytes"]
                cursor = connection.execute(
                    "SELECT CASE WHEN typeof(raw) = 'blob' AND length(raw) <= ? THEN raw END, "
                    + ", ".join(
                        "CASE WHEN typeof("
                        + column
                        + ") = 'text' AND length(CAST("
                        + column
                        + " AS BLOB)) <= ? THEN "
                        + column
                        + " END"
                        for column in ("category", "file", "message")
                    )
                    + " FROM findings"
                    + where
                    + " ORDER BY ordinal LIMIT ? OFFSET ?",
                    [cap] * 4 + params + [per_page, (page - 1) * per_page],
                )
                for raw, row_category, row_file, row_message in cursor:
                    check()
                    if raw is None:
                        raise IntegrityError("Index row exceeds raw BLOB/item profile")
                    used += len(raw)
                    if used > max_page_bytes:
                        raise ContractError(
                            "Result page byte budget exceeded; reduce per_page"
                        )
                    row = _finding(raw, validator)
                    if (row_category, row_file, row_message) != (
                        row["category"],
                        row["file"],
                        row["message"],
                    ):
                        raise IntegrityError(
                            "Index search columns contradict retained raw finding"
                        )
                    items.append(row)
                response = {
                    "items": items,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "total_pages": max(1, (total + per_page - 1) // per_page),
                    "source": {
                        **deepcopy(request["source"]),
                        "status": original_manifest["status"],
                        "input_verification": original_manifest.get(
                            "input_verification", "unverified"
                        ),
                    },
                    "read_scope": "selected_artifact_only",
                    "analysis_cache_eligible": False,
                    "index": {
                        "run_id": self.snapshot.run_id,
                        "manifest_sha256": self.snapshot.manifest_sha256,
                        "sha256": entry["sha256"],
                        "index_version": VERSION,
                        "stream_version": STREAM_VERSION,
                    },
                    "limitations": list(_LIMITATIONS),
                }
                if len(canonical_json_bytes(response)) > max_page_bytes:
                    raise ContractError(
                        "Result page response byte budget exceeded; reduce per_page"
                    )
                database.verify()
                guard()
                self.snapshot.verify()
                guard()
                database.guard()
                self.snapshot._check_manifest()
                _cache_protocol(self.snapshot)
                guard(identity_only=True)
                database.guard()
                check()
                return response
            except sqlite3.Error as error:
                raise IntegrityError("Read-only result index query failed") from error
            finally:
                if connection is not None:
                    connection.close()
                database.close()


def build_result_index(source_store, cache_root, request) -> ResultIndex:
    """Build and publish one all-or-nothing byte-derived index, or verify reuse."""
    request = deepcopy(request)
    validate_index_request(request)
    store = _store(source_store)
    check = _deadline(request["limits"]["wall_seconds"])
    cache = RunStore(_cache_path(store, cache_root, request))
    with _selected(store, request, check) as (manifest, artifact, guard):
        # Existing authority is never silently repaired, deleted or replaced.
        from cppulse.store_heads import read_heads

        heads = read_heads(cache.root)
        if heads["latest"] is not None:
            snapshot = _open_cached(
                cache,
                heads["latest"],
                request,
                check,
                original_source=manifest["source"],
            )
            receipt = _receipt(
                snapshot, request, original_source=manifest["source"], check=check
            )
            _verify_database(snapshot, request, receipt, check)
            guard()
            return ResultIndex(store, snapshot, request, True)
        with (
            _directory(cache.root.parent) as cold_parent,
            publication_guard(
                cold_parent, timeout_seconds=0, required=True
            ) as cold_lease,
        ):
            cold_lease.check()
            # Another builder might have completed between the first head read
            # and lease acquisition. Reuse only after checking that exact head.
            latest = read_heads(cache.root)["latest"]
            if latest is not None:
                snapshot = _open_cached(
                    cache, latest, request, check, original_source=manifest["source"]
                )
                receipt = _receipt(
                    snapshot, request, original_source=manifest["source"], check=check
                )
                _verify_database(snapshot, request, receipt, check)
                guard()
                return ResultIndex(store, snapshot, request, True)
            original_guard = guard
            cold_identity = _identity(os.fstat(cold_parent))[:2]

            def guard():
                cold_lease.check()
                with _directory(cache.root.parent) as current:
                    if _identity(os.fstat(current))[:2] != cold_identity:
                        raise IntegrityError(
                            "Cold-build cache parent directory changed"
                        )
                original_guard()

            candidate = cache.root / ".candidates" / uuid4().hex
            with _directory(candidate, create=True) as candidate_fd:
                candidate_identity = _identity(os.fstat(candidate_fd))[:2]

                def candidate_guard():
                    with _directory(candidate) as current:
                        if _identity(os.fstat(current))[:2] != candidate_identity:
                            raise IntegrityError(
                                "Owned index candidate directory changed"
                            )
                    check()

                database = candidate / "index.sqlite"
                connection = None
                try:
                    _write_new(database, b"", parent_fd=candidate_fd)
                    candidate_guard()
                    connection = _connect(database, request["limits"], check)
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute(_TABLE_SQL)
                    for statement in _INDEX_SQL.values():
                        connection.execute(statement)
                    validator = _finding_validator()
                    limits = replace(
                        JsonStreamLimits(),
                        max_bytes=request["source"]["size_bytes"],
                        max_item_bytes=request["limits"]["max_item_bytes"],
                        max_records=request["limits"]["max_rows"],
                        max_array_items=10_000_000,
                    )
                    count = 0
                    artifact.guard()
                    for raw in iter_json_array(
                        artifact,
                        "findings",
                        expected_sha256=request["source"]["sha256"],
                        expected_size=request["source"]["size_bytes"],
                        limits=limits,
                    ):
                        candidate_guard()
                        row = _finding(raw, validator)
                        connection.execute(
                            "INSERT INTO findings VALUES (?,?,?,?,?)",
                            (count, row["category"], row["file"], row["message"], raw),
                        )
                        count += 1
                    guard()
                    check()
                    candidate_guard()
                    connection.commit()
                    connection.close()
                    connection = None
                    if database.stat().st_size > request["limits"]["max_index_bytes"]:
                        raise ContractError(
                            "Result index database byte budget exceeded"
                        )
                    receipt = {
                        "version": VERSION,
                        "index_version": VERSION,
                        "stream_version": STREAM_VERSION,
                        "request": request,
                        "complete": True,
                        "rows": count,
                        "native_executed": False,
                        "analysis_cache_eligible": False,
                        "read_scope": "selected_artifact_only",
                        "limitations": list(_LIMITATIONS),
                    }
                    raw_receipt = canonical_json_bytes(receipt)
                    if len(raw_receipt) > _RECEIPT_LIMIT:
                        raise ContractError("Result index receipt budget exceeded")
                    _write_new(
                        candidate / "receipt.json", raw_receipt, parent_fd=candidate_fd
                    )
                    candidate_guard()
                    source_guard = guard

                    def publish_guard():
                        candidate_guard()
                        source_guard()

                    with cache.begin() as stage:
                        entries = [
                            stage.copy_artifact("index", database, "index.sqlite"),
                            stage.copy_artifact(
                                "receipt", candidate / "receipt.json", "receipt.json"
                            ),
                        ]
                        now = datetime.now(timezone.utc).isoformat()
                        derived = {
                            "version": "2.0.0",
                            "run_id": stage.run_id,
                            "status": "completed",
                            "source": deepcopy(manifest["source"]),
                            "contexts": [],
                            "stages": [],
                            "artifacts": entries,
                            "started_at": now,
                            "finished_at": now,
                            "config_digest": _digest(request),
                            "versions": dict(_VERSIONS),
                            "limitations": list(_LIMITATIONS),
                        }
                        snapshot = stage.publish(derived, material_check=publish_guard)
                    return ResultIndex(store, snapshot, request, False)
                except BaseException as error:
                    if connection is not None:
                        try:
                            connection.rollback()
                        finally:
                            connection.close()
                    # Failures are retained, not renamed into completed runs or deleted.
                    _write_new(
                        candidate / "failure.json",
                        canonical_json_bytes(
                            {
                                "status": "failed",
                                "type": type(error).__name__,
                                "message": str(error)[:2048],
                                "request": request,
                                "partial_rows_visible": False,
                            }
                        ),
                        parent_fd=candidate_fd,
                    )
                    if isinstance(error, sqlite3.Error):
                        raise ContractError(
                            "Result index SQLite construction failed or exceeded budget"
                        ) from error
                    raise
