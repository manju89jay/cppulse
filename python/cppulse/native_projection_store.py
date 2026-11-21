"""Ephemeral compressed structural projections, never normalized evidence/cache."""

# Closed finite profiles deliberately reject bools and subclasses.
# ruff: noqa: E721
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import uuid
import zlib

from cppulse.contracts.json_projection import (
    ProjectionComplete,
    ProjectionRecord,
    validate_selectors,
    VERSION,
)
from cppulse.contracts.json_stream import VERSION as BASE_VERSION
from cppulse.errors import ContractError, IntegrityError


@dataclass(frozen=True, slots=True)
class ProjectionStoreLimits:
    """Logical database/record caps; filesystem allocation remains caller-owned."""

    max_record_bytes: int = 16 * 1024**2
    max_records: int = 100_000
    max_database_bytes: int = 96 * 1024**2

    def validate(self):
        if type(self) is not ProjectionStoreLimits:
            raise ContractError("Exact projection store limits required")
        for name, low, high in [
            ("max_record_bytes", 1, 32 * 1024**2),
            ("max_records", 1, 10_000_000),
            ("max_database_bytes", 12288, 1024**3),
        ]:
            v = getattr(self, name)
            if type(v) is not int or not low <= v <= high:
                raise ContractError("Invalid projection store bound: " + name)


class ProjectionStore:
    """A reader available only after transactional producer completion."""

    def __init__(self, db, fd, path, completion, selectors, limits):
        self._db = db
        self._fd = fd
        self.path = path
        self.completion = completion
        self._selectors = {s.name: s for s in selectors}
        self._limits = limits
        self._counts = dict(completion.counts)
        self._identity = self._fingerprint(os.fstat(fd))
        self._closed = False

    @staticmethod
    def _fingerprint(info):
        return (
            info.st_dev,
            info.st_ino,
            info.st_mode,
            info.st_uid,
            info.st_gid,
            info.st_nlink,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )

    def _check(self):
        if self._closed:
            raise ContractError("Projection reader is closed")
        try:
            info = self.path.lstat()
            current = os.fstat(self._fd)
        except OSError as e:
            raise IntegrityError("Projection stage disappeared") from e
        if (
            self._fingerprint(info) != self._identity
            or self._fingerprint(current) != self._identity
            or current.st_size > self._limits.max_database_bytes
        ):
            raise IntegrityError("Sealed projection stage changed")

    def _selector(self, name):
        self._check()
        if type(name) is not str or name not in self._selectors:
            raise ContractError("Unknown projection selector")
        return self._selectors[name]

    def record_count(self, selector):
        self._selector(selector)
        return self._counts[selector]

    def raw_value(self, selector):
        if self._selector(selector).mode != "value":
            raise ContractError("Value reader requires a value selector")
        return self.get_raw(selector, None) if self._counts[selector] else None

    def iter_raw(self, selector):
        if self._selector(selector).mode != "array":
            raise ContractError("Array reader requires an array selector")

        def iterate():
            self._check()
            for ordinal in range(self._counts[selector]):
                yield self.get_raw(selector, ordinal)
            self._check()

        return iterate()

    def get_raw(self, selector, ordinal):
        sel = self._selector(selector)
        if (sel.mode == "value" and ordinal is not None) or (
            sel.mode == "array"
            and (type(ordinal) is not int or not 0 <= ordinal < self._counts[selector])
        ):
            raise ContractError("Projection ordinal out of range")
        try:
            row = self._db.execute(
                "SELECT rawlen, sha256, length(payload) FROM records WHERE selector=? AND ordinal=?",
                (selector, -1 if ordinal is None else ordinal),
            ).fetchone()
            if row is None:
                raise IntegrityError("Projection record missing")
            length, digest, compressed = row
            if (
                type(length) is not int
                or not 1 <= length <= self._limits.max_record_bytes
                or type(compressed) is not int
                or not 1 <= compressed <= self._limits.max_record_bytes + 65536
            ):
                raise IntegrityError("Projection compressed record bounds invalid")
            payload = self._db.execute(
                "SELECT payload FROM records WHERE selector=? AND ordinal=?",
                (selector, -1 if ordinal is None else ordinal),
            ).fetchone()[0]
            if type(payload) is not bytes:
                raise IntegrityError("Projection compressed payload type invalid")
            dec = zlib.decompressobj()
            raw = dec.decompress(payload, length + 1)
            if (
                len(raw) != length
                or not dec.eof
                or dec.unused_data
                or dec.unconsumed_tail
                or hashlib.sha256(raw).hexdigest() != digest
            ):
                raise IntegrityError("Projection compressed record integrity failed")
            self._check()
            return raw
        except (sqlite3.Error, zlib.error) as e:
            raise IntegrityError("Projection database/deflate integrity failed") from e


@contextmanager
def stage_projection(
    events,
    *,
    selectors,
    expected_sha256,
    expected_size,
    directory,
    source_guard,
    limits=ProjectionStoreLimits(),
):
    """Validate a complete provisional stream before yielding its private reader."""
    if type(limits) is not ProjectionStoreLimits:
        raise ContractError("Exact projection store limits required")
    limits.validate()
    selectors = validate_selectors(selectors)
    if (
        type(expected_sha256) is not str
        or re.fullmatch("[a-f0-9]{64}", expected_sha256) is None
        or type(expected_size) is not int
        or not 0 <= expected_size <= 16 * 1024**3
        or not isinstance(directory, Path)
        or not callable(source_guard)
    ):
        raise ContractError("Invalid projection store arguments")

    try:
        events = iter(events)
    except TypeError as error:
        raise ContractError("Projection events require an iterable") from error
    try:
        encoded_directory = os.fsencode(directory)
    except (UnicodeError, ValueError) as error:
        raise ContractError("Invalid projection stage directory") from error
    if b"\0" in encoded_directory:
        raise ContractError("Invalid projection stage directory")

    def guard():
        if source_guard() is not None:
            raise ContractError("Source guard must return None")

    guard()
    dirfd = fd = None
    db = reader = None
    name = "projection-" + uuid.uuid4().hex + ".sqlite"
    identity = None
    try:
        dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fd = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=dirfd,
        )
        identity = os.fstat(fd)
        path = directory / name
        db = sqlite3.connect("/proc/self/fd/" + str(fd), isolation_level=None)
        db.enable_load_extension(False)
        db.execute("PRAGMA page_size=4096")
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute("PRAGMA cache_size=-512")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA max_page_count=" + str(limits.max_database_bytes // 4096))
        db.execute("BEGIN")
        db.execute(
            "CREATE TABLE records(selector TEXT NOT NULL, ordinal INTEGER NOT NULL, rawlen INTEGER NOT NULL, sha256 TEXT NOT NULL, payload BLOB NOT NULL, PRIMARY KEY(selector,ordinal)) WITHOUT ROWID"
        )
        counts = {s.name: 0 for s in selectors}
        declared = {s.name: s for s in selectors}
        completion = None
        total = 0
        for event in events:
            if completion is not None:
                raise ContractError("Event after projection completion")
            if type(event) is ProjectionComplete:
                event.__post_init__()
                if (
                    event.kind != "complete"
                    or event.base_stream_version != BASE_VERSION
                    or event.version != VERSION
                    or event.number_policy != "finite-python-json"
                    or event.read_scope != "structural_projection"
                    or any(
                        getattr(event, field) is not False
                        for field in (
                            "schema_verified",
                            "source_verified",
                            "native_executed",
                            "analysis_cache_eligible",
                        )
                    )
                ):
                    raise ContractError(
                        "Projection completion qualification flags changed"
                    )
                completion = event
                if (
                    event.sha256 != expected_sha256
                    or event.size_bytes != expected_size
                    or event.counts != tuple(counts.items())
                    or event.present
                    != tuple(s.name for s in selectors if s.name in event.present)
                ):
                    raise ContractError(
                        "Projection completion pins/order/counts disagree"
                    )
                for s in selectors:
                    if (
                        (s.required and s.name not in event.present)
                        or (counts[s.name] and s.name not in event.present)
                        or (
                            s.mode == "value"
                            and ((s.name in event.present) != (counts[s.name] == 1))
                        )
                    ):
                        raise ContractError(
                            "Projection completion presence/mode mismatch"
                        )
                continue
            if type(event) is not ProjectionRecord or event.selector not in declared:
                raise ContractError("Undeclared projection event")
            event.__post_init__()
            if event.kind != "record":
                raise ContractError("Invalid projection record discriminator")
            s = declared[event.selector]
            expected = counts[s.name] if s.mode == "array" else None
            if (
                event.ordinal != expected
                or (s.mode == "array" and type(event.ordinal) is not int)
                or (s.mode == "value" and counts[s.name])
            ):
                raise ContractError("Projection ordinal/mode mismatch")
            if len(event.raw) > limits.max_record_bytes or total >= limits.max_records:
                raise ContractError("Projection record/count budget exceeded")
            payload = zlib.compress(event.raw)
            db.execute(
                "INSERT INTO records VALUES(?,?,?,?,?)",
                (
                    s.name,
                    -1 if event.ordinal is None else event.ordinal,
                    len(event.raw),
                    hashlib.sha256(event.raw).hexdigest(),
                    payload,
                ),
            )
            counts[s.name] += 1
            total += 1
        if completion is None:
            raise ContractError("Projection did not complete")
        info = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
        if (info.st_dev, info.st_ino) != (identity.st_dev, identity.st_ino):
            raise IntegrityError("Owned projection stage replaced")
        db.commit()
        guard()
        db.execute("PRAGMA query_only=ON")
        for selector in selectors:
            count, first, last = db.execute(
                "SELECT count(*), min(ordinal), max(ordinal) FROM records WHERE selector=?",
                (selector.name,),
            ).fetchone()
            expected = counts[selector.name]
            if count != expected or (
                expected
                and (
                    first != (0 if selector.mode == "array" else -1)
                    or last != (expected - 1 if selector.mode == "array" else -1)
                )
            ):
                raise IntegrityError("Projection stored count/ordinal mismatch")
        reader = ProjectionStore(db, fd, path, completion, selectors, limits)
        reader._check()
        yield reader
    except sqlite3.Error as e:
        raise ContractError("Projection database budget/storage failure") from e
    finally:
        if reader is not None:
            reader._closed = True
        if db is not None:
            db.close()
        if fd is not None:
            os.close(fd)
        if dirfd is not None:
            try:
                info = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
                if identity is not None and (info.st_dev, info.st_ino) == (
                    identity.st_dev,
                    identity.st_ino,
                ):
                    os.unlink(name, dir_fd=dirfd)
            except FileNotFoundError:
                pass
            finally:
                os.close(dirfd)
