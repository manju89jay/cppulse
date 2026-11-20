"""Ephemeral indexed equivalent of the literal thirty-token duplication profile."""
# Closed finite budgets deliberately exclude bool and subclasses.
# ruff: noqa: E721
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import struct
import uuid

from cppulse.errors import ContractError, IntegrityError
from cppulse.measurements import DuplicateCount


@dataclass(frozen=True, slots=True)
class DuplicationIndexLimits:
    max_files: int = 100000
    max_file_id_bytes_total: int = 16 * 1024**2
    max_token_records_total: int = 10000000
    max_database_bytes: int = 256 * 1024**2

    def validate(self):
        if type(self) is not DuplicationIndexLimits:
            raise ContractError("Exact duplication limits required")
        for name, low, high in [
            ("max_files", 1, 100000),
            ("max_file_id_bytes_total", 1, 16 * 1024**2),
            ("max_token_records_total", 1, 10000000),
            ("max_database_bytes", 12288, 1024**3),
        ]:
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ContractError("Invalid duplication budget: " + name)


def _fingerprint(ids):
    return hashlib.sha256(struct.pack(">30Q", *ids)).digest()


def _text(value):
    if type(value) is not str:
        raise ContractError("Duplication identity requires literal strings")
    try:
        return value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ContractError("Duplication identity contains invalid Unicode") from error


def _union(rows):
    """Yield disjoint inclusive intervals from an already indexed ordered cursor."""
    first = last = None
    for start, end in rows:
        if first is None:
            first, last = start, end
        elif start <= last + 1:
            last = max(last, end)
        else:
            yield first, last
            first, last = start, end
    if first is not None:
        yield first, last


def indexed_duplicate_token_counts(
    streams,
    *,
    directory: Path,
    minimum_tokens=30,
    limits=DuplicationIndexLimits(),
    scope_complete: bool | None = None,
):
    """Return exact unions after input EOF; no producer/schema/authentication proof."""
    if type(limits) is not DuplicationIndexLimits:
        raise ContractError("Exact duplication limits required")
    limits.validate()
    if scope_complete is not None and type(scope_complete) is not bool:
        raise ContractError("Duplication scope completeness must be exact bool or None")
    if (
        type(minimum_tokens) is not int
        or minimum_tokens != 30
        or not isinstance(directory, Path)
    ):
        raise ContractError("The literal duplication profile requires thirty tokens")
    try:
        streams = iter(streams)
    except TypeError as error:
        raise ContractError("Duplication streams must be iterable") from error
    dirfd = fd = db = None
    identity = None
    name = "duplication-" + uuid.uuid4().hex + ".sqlite"
    try:
        dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fd = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=dirfd,
        )
        identity = os.fstat(fd)
        db = sqlite3.connect("/proc/self/fd/" + str(fd), isolation_level=None)
        db.enable_load_extension(False)
        for pragma in [
            "page_size=4096",
            "journal_mode=OFF",
            "synchronous=OFF",
            "temp_store=MEMORY",
            "cache_size=-1024",
            "trusted_schema=OFF",
        ]:
            db.execute("PRAGMA " + pragma)
        db.execute("PRAGMA max_page_count=" + str(limits.max_database_bytes // 4096))
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, limits.max_database_bytes)
        db.execute("BEGIN")
        for statement in [
            "CREATE TABLE files(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)",
            "CREATE TABLE literals(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, spelling TEXT NOT NULL, UNIQUE(kind,spelling))",
            "CREATE TABLE tokens(file INTEGER NOT NULL,pos INTEGER NOT NULL,literal INTEGER NOT NULL,line INTEGER NOT NULL,last INTEGER NOT NULL,PRIMARY KEY(file,pos)) WITHOUT ROWID",
            "CREATE TABLE groups(id INTEGER PRIMARY KEY,hash BLOB NOT NULL,file INTEGER NOT NULL,pos INTEGER NOT NULL,multiple INTEGER NOT NULL,minimum INTEGER NOT NULL,maximum INTEGER NOT NULL)",
            "CREATE INDEX group_hash ON groups(hash)",
            "CREATE TABLE windows(file INTEGER NOT NULL,pos INTEGER NOT NULL,gid INTEGER NOT NULL,PRIMARY KEY(file,pos)) WITHOUT ROWID",
            "CREATE TABLE matches(file INTEGER NOT NULL,start INTEGER NOT NULL,last INTEGER NOT NULL,PRIMARY KEY(file,start)) WITHOUT ROWID",
            "CREATE TABLE lines(file INTEGER NOT NULL,start INTEGER NOT NULL,last INTEGER NOT NULL,PRIMARY KEY(file,start,last)) WITHOUT ROWID",
        ]:
            db.execute(statement)
        metadata = total = files = 0
        unknown = False
        for item in streams:
            if type(item) not in (tuple, list) or len(item) != 2:
                raise ContractError("Invalid duplication file frame")
            file, frame = item
            if (
                type(file) is not str
                or len(file) > limits.max_file_id_bytes_total - metadata
            ):
                raise ContractError("Duplication file identity byte budget exceeded")
            metadata += len(_text(file))
            files += 1
            if files > limits.max_files or metadata > limits.max_file_id_bytes_total:
                raise ContractError("Duplication file/identity budget exceeded")
            if (
                type(frame) is not dict
                or type(frame.get("complete")) is not bool
                or type(frame.get("availability")) is not str
            ):
                raise ContractError("Malformed duplication availability frame")
            try:
                db.execute("INSERT INTO files VALUES(?,?)", (files, file))
            except sqlite3.IntegrityError as error:
                raise ContractError("Duplicate duplication file ID") from error
            complete = frame["complete"] and frame["availability"] == "measured"
            unknown = unknown or not complete
            if not complete:
                partial_records = frame.get("records", ())
                if type(partial_records) not in (list, tuple):
                    raise ContractError("Invalid partial token record sequence")
                total += len(partial_records)
                if total > limits.max_token_records_total:
                    raise ContractError("Duplication token budget exceeded")
                partial_records = frame = item = None
                continue
            records = frame.get("records")
            if type(records) not in (list, tuple):
                raise ContractError("Measured tokens require decoded record sequence")
            window = deque(maxlen=30)
            for pos, row in enumerate(records):
                total += 1
                if total > limits.max_token_records_total:
                    raise ContractError("Duplication token budget exceeded")
                if type(row) is not dict:
                    raise ContractError("Malformed duplication token")
                kind = row.get("kind")
                spelling = row.get("spelling")
                _text(kind)
                _text(spelling)
                line = row.get("line")
                end = row.get("end_line")
                column = row.get("end_column")
                if (
                    any(
                        type(v) is not int or not 1 <= v <= 2**63 - 1
                        for v in (line, end, column)
                    )
                    or end < line
                ):
                    raise ContractError("Malformed duplication token geometry")
                last = end - int(end > line and column == 1)
                if unknown or scope_complete is False:
                    continue
                db.execute(
                    "INSERT OR IGNORE INTO literals(kind,spelling) VALUES(?,?)",
                    (kind, spelling),
                )
                literal = db.execute(
                    "SELECT id FROM literals WHERE kind=? AND spelling=?",
                    (kind, spelling),
                ).fetchone()[0]
                db.execute(
                    "INSERT INTO tokens VALUES(?,?,?,?,?)",
                    (files, pos, literal, line, last),
                )
                window.append(literal)
                if len(window) < 30 or unknown:
                    continue
                start = pos - 29
                gid = None
                for candidate, peer, offset in db.execute(
                    "SELECT id,file,pos FROM groups WHERE hash=?",
                    (_fingerprint(window),),
                ):
                    # A digest selects candidates only. Literal intern IDs verify
                    # every one of the thirty identities without hash assumptions.
                    ids = tuple(
                        v[0]
                        for v in db.execute(
                            "SELECT literal FROM tokens WHERE file=? AND pos BETWEEN ? AND ? ORDER BY pos",
                            (peer, offset, offset + 29),
                        )
                    )
                    if ids == tuple(window):
                        gid = candidate
                        break
                if gid is None:
                    gid = db.execute(
                        "INSERT INTO groups(hash,file,pos,multiple,minimum,maximum) VALUES(?,?,?,0,?,?)",
                        (_fingerprint(window), files, start, start, start),
                    ).lastrowid
                else:
                    db.execute(
                        "UPDATE groups SET multiple=multiple OR file!=?,minimum=min(minimum,?),maximum=max(maximum,?) WHERE id=?",
                        (files, start, start, gid),
                    )
                db.execute("INSERT INTO windows VALUES(?,?,?)", (files, start, gid))
            # Drop this file before asking an upstream generator for its peer.
            records = frame = item = row = None
            window.clear()
        if scope_complete is not None and scope_complete != (not unknown):
            raise ContractError(
                "Declared duplication scope completeness disagrees with actual frames"
            )
        result = {}
        if unknown:
            current = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise IntegrityError("Owned duplication stage replaced")
            for _, file in db.execute("SELECT id,name FROM files ORDER BY id"):
                result[file] = DuplicateCount(
                    None, None, ("Selected token scope is incomplete.",)
                )
            return result
        db.execute(
            "INSERT INTO matches SELECT w.file,w.pos,w.pos+29 FROM windows w JOIN groups g ON g.id=w.gid WHERE g.multiple OR w.pos-g.minimum>=30 OR g.maximum-w.pos>=30"
        )
        for fileid, file in db.execute("SELECT id,name FROM files ORDER BY id"):
            token_count = 0
            for start, last in _union(
                db.execute(
                    "SELECT start,last FROM matches WHERE file=? ORDER BY start",
                    (fileid,),
                )
            ):
                token_count += last - start + 1
                db.execute(
                    "INSERT OR IGNORE INTO lines SELECT file,line,last FROM tokens WHERE file=? AND pos BETWEEN ? AND ?",
                    (fileid, start, last),
                )
            line_count = sum(
                last - start + 1
                for start, last in _union(
                    db.execute(
                        "SELECT start,last FROM lines WHERE file=? ORDER BY start,last",
                        (fileid,),
                    )
                )
            )
            result[file] = DuplicateCount(token_count, line_count)
        db.commit()
        info = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
        if (info.st_dev, info.st_ino) != (identity.st_dev, identity.st_ino):
            raise IntegrityError("Owned duplication stage replaced")
        return result
    except sqlite3.Error as error:
        raise ContractError("Duplication SQLite budget/storage failure") from error
    finally:
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
