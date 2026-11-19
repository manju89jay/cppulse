"""Bounded one-file reuse of the frozen native-metric semantic validator."""
# Exact finite budgets intentionally exclude booleans and subclasses.
# ruff: noqa: E721
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sqlite3
import uuid

from cppulse.contracts.maintenance import validate_native_metrics
from cppulse.errors import ContractError, IntegrityError


@dataclass(frozen=True, slots=True)
class NativeMetricsLimits:
    max_files: int = 100000
    max_database_bytes: int = 32 * 1024**2
    max_path_bytes: int = 4096

    def validate(self):
        if type(self) is not NativeMetricsLimits:
            raise ContractError("Exact native metric limits required")
        for name, low, high in [
            ("max_files", 1, 100000),
            ("max_database_bytes", 8192, 1024**3),
            ("max_path_bytes", 1, 1024**2),
        ]:
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ContractError("Invalid native metric bound: " + name)


@dataclass(frozen=True, slots=True)
class NativeMetricsCheck:
    """Semantic parity/counts only; all independent qualification flags stay false."""

    checked: bool
    analysis_file_count: int
    metric_file_count: int
    schema_verified: bool = field(default=False, init=False)
    source_verified: bool = field(default=False, init=False)
    native_executed: bool = field(default=False, init=False)
    analysis_cache_eligible: bool = field(default=False, init=False)


def _path(row, limits):
    if not isinstance(row, dict):
        raise ContractError("Native metric rows require dictionaries")
    path = row.get("path")
    if type(path) is not str or len(path) > limits.max_path_bytes:
        raise ContractError("Native metric path exceeds finite bound")
    try:
        if len(path.encode("utf-8", errors="strict")) > limits.max_path_bytes:
            raise ContractError("Native metric UTF8 path exceeds finite bound")
    except UnicodeError as error:
        raise ContractError("Native metric path has invalid Unicode") from error
    return path


def validate_streamed_native_metrics(
    analysis_files,
    metric_files,
    *,
    metrics_header,
    directory: Path,
    limits=NativeMetricsLimits(),
):
    """Consume each inventory once; publish no partial semantic success."""
    if type(limits) is not NativeMetricsLimits:
        raise ContractError("Exact native metric limits required")
    limits.validate()
    if not isinstance(directory, Path):
        raise ContractError("Native metric staging requires a directory Path")
    if metrics_header is None:
        return NativeMetricsCheck(False, 0, 0)
    if not isinstance(metrics_header, dict) or "files" in metrics_header:
        raise ContractError("Native metric header must exclude file payloads")
    # Freeze the small schema-checked header without retaining caller file arrays.
    header = dict(metrics_header)
    try:
        analysis_files = iter(analysis_files)
        metric_files = iter(metric_files)
    except TypeError as error:
        raise ContractError("Native metric inventories must be iterable") from error
    dirfd = fd = db = None
    identity = None
    name = "native-metrics-" + uuid.uuid4().hex + ".sqlite"
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
        for setting in [
            "page_size=4096",
            "journal_mode=OFF",
            "synchronous=OFF",
            "temp_store=MEMORY",
            "cache_size=-512",
            "trusted_schema=OFF",
        ]:
            db.execute("PRAGMA " + setting)
        db.execute("PRAGMA max_page_count=" + str(limits.max_database_bytes // 4096))
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, limits.max_database_bytes)
        db.execute("BEGIN")
        db.execute(
            "CREATE TABLE coverage(path TEXT PRIMARY KEY,status TEXT NOT NULL,errors TEXT NOT NULL,seen INTEGER NOT NULL) WITHOUT ROWID"
        )
        analysis_count = metric_count = 0
        for row in analysis_files:
            analysis_count += 1
            if analysis_count > limits.max_files:
                raise ContractError("Native analysis file count exceeds bound")
            path = _path(row, limits)
            try:
                db.execute(
                    "INSERT INTO coverage VALUES(?,?,?,0)",
                    (
                        path,
                        row["status"],
                        json.dumps(row["error_count"], allow_nan=False),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ContractError("Duplicate native analysis path") from error
            row = None
        for row in metric_files:
            metric_count += 1
            if metric_count > limits.max_files:
                raise ContractError("Native metric file count exceeds bound")
            path = _path(row, limits)
            stored = db.execute(
                "SELECT status,errors,seen FROM coverage WHERE path=?", (path,)
            ).fetchone()
            if stored is None:
                raise ContractError("Native metric path absent from parse inventory")
            status, errors, seen = stored
            if seen:
                raise ContractError("Duplicate native metric path")
            descriptor = {
                "path": path,
                "status": status,
                "error_count": json.loads(errors),
            }
            envelope = {
                "metadata": {
                    "analysis": {
                        "files": [descriptor],
                        "native_metrics": {**header, "files": [row]},
                    }
                }
            }
            validate_native_metrics(envelope)
            db.execute("UPDATE coverage SET seen=1 WHERE path=?", (path,))
            # Drop all large payload aliases before requesting the next row.
            envelope = row = None
        if (
            analysis_count != metric_count
            or db.execute("SELECT 1 FROM coverage WHERE seen=0 LIMIT 1").fetchone()
            is not None
        ):
            raise ContractError(
                "Native metrics and parse inventory cover different files"
            )
        info = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
        if (info.st_dev, info.st_ino) != (identity.st_dev, identity.st_ino):
            raise IntegrityError("Owned native metric stage replaced")
        db.commit()
        return NativeMetricsCheck(True, analysis_count, metric_count)
    except sqlite3.Error as error:
        raise ContractError("Native metric SQLite capacity/storage failure") from error
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
