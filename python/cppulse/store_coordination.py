"""Cooperative local filesystem serialization and process-incarnation facts."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from functools import lru_cache
import json
import os
from pathlib import Path
import stat
import sys
import time
from typing import Any, Iterator

import jsonschema

from cppulse.errors import ContractError, IntegrityError, PublicationConflict

GUARD_NAME = ".coordination.lock"


@lru_cache(maxsize=4)
def _schema(name: str) -> dict[str, Any]:
    path = resources.files("cppulse.contracts").joinpath(
        "schemas", "store_private", name + ".schema.json"
    )
    return json.loads(path.read_text())


def validate_store_document(name: str, document: dict[str, Any]) -> None:
    """Validate private store protocol JSON without retrieving remote schemas."""
    errors = list(
        jsonschema.Draft7Validator(
            _schema(name), format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER
        ).iter_errors(document)
    )
    if errors:
        raise ContractError("Invalid private store " + name + ": " + errors[0].message)


def _proc_bytes(path: Path, maximum: int = 16384) -> bytes:
    with path.open("rb") as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise IntegrityError("Process identity observation exceeds its finite budget")
    return value


def process_incarnation(pid: int) -> dict[str, Any]:
    """Observe Linux start ticks and namespace without signalling any process."""
    if (
        sys.platform != "linux"
        or not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid < 1
    ):
        raise IntegrityError(
            "Process incarnation observation requires Linux and a positive PID"
        )
    raw = _proc_bytes(Path("/proc") / str(pid) / "stat")
    try:
        prefix, suffix = raw.rsplit(b") ", 1)
        actual = int(prefix.split(b" (", 1)[0])
        fields = suffix.split()
        ticks = int(fields[19])
        state = fields[0].decode("ascii")
    except (ValueError, IndexError, UnicodeError) as exc:
        raise IntegrityError("Process incarnation data is incomplete") from exc
    if actual != pid or ticks <= 0:
        raise IntegrityError("Process incarnation does not identify the selected PID")
    namespace = os.stat(Path("/proc") / str(pid) / "ns/pid")
    owner = os.stat(Path("/proc") / str(pid))
    return {
        "pid": pid,
        "start_ticks": ticks,
        "pid_namespace": f"{namespace.st_dev}:{namespace.st_ino}",
        "uid": owner.st_uid,
        "state": state,
    }


def local_process_identity() -> dict[str, Any]:
    """Record qualified local Linux identity or explicit unavailable facts."""
    try:
        current = process_incarnation(os.getpid())
        boot = (
            _proc_bytes(Path("/proc/sys/kernel/random/boot_id"), 128)
            .strip()
            .decode("ascii")
        )
        return {
            "status": "available",
            "boot_id": boot,
            "start_ticks": current["start_ticks"],
            "pid_namespace": current["pid_namespace"],
            "uid": current["uid"],
            "reason": "",
        }
    except (OSError, ValueError, IntegrityError) as exc:
        return {
            "status": "unavailable",
            "boot_id": None,
            "start_ticks": None,
            "pid_namespace": None,
            "uid": None,
            "reason": str(exc),
        }


def new_lock_document(run_id: str, token: str) -> dict[str, Any]:
    """Create the current writer-lock protocol without claiming source freshness."""
    result = {
        "version": "2.0.0",
        "run_id": run_id,
        "token": token,
        "pid": os.getpid(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "owner": local_process_identity(),
    }
    validate_store_document("publication_lock", result)
    return result


@dataclass(frozen=True)
class CoordinationLease:
    """One live local flock, tied to the permanent selected guard inode."""

    root_fd: int
    descriptor: int | None
    device: int | None
    inode: int | None

    def check(self) -> None:
        """Refuse renamed, linked or replaced guard files during coordination."""
        if self.descriptor is None:
            return
        current = os.fstat(self.descriptor)
        named = os.stat(GUARD_NAME, dir_fd=self.root_fd, follow_symlinks=False)
        if any(
            (item.st_dev, item.st_ino) != (self.device, self.inode)
            or not stat.S_ISREG(item.st_mode)
            or item.st_nlink != 1
            or item.st_uid != os.geteuid()
            or stat.S_IMODE(item.st_mode) != 0o600
            for item in (current, named)
        ):
            raise PublicationConflict(
                "Publication coordination guard changed or is unsafe"
            )


@contextmanager
def publication_guard(
    root_fd: int, *, timeout_seconds: float = 1.0, required: bool = False
) -> Iterator[CoordinationLease]:
    """Serialize cooperative writers/recovery; kernel releases the lock on death.

    The permanent guard is never removed or renamed. Unsupported platforms keep
    the historical exclusive publication-token behavior, but cannot recover.
    """
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or not 0 <= timeout_seconds <= 10
    ):
        raise ContractError(
            "Coordination timeout must be finite and within zero to ten seconds"
        )
    if os.name != "posix":
        if required:
            raise IntegrityError("Safe store recovery requires qualified POSIX locking")
        yield CoordinationLease(root_fd, None, None, None)
        return
    import fcntl

    try:
        descriptor = os.open(
            GUARD_NAME,
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=root_fd,
        )
    except OSError as exc:
        raise PublicationConflict(
            "Publication coordination guard is unsafe or unavailable"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        lease = CoordinationLease(root_fd, descriptor, metadata.st_dev, metadata.st_ino)
        lease.check()
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise PublicationConflict(
                        "Store publication/recovery is busy; retry after the active local transaction"
                    ) from exc
                time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        lease.check()
        try:
            yield lease
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)
