"""Pure local content identities for finite source inventories and build contexts.

These hashes identify bytes and settings; they do not authenticate a producer.
Snapshots verify explicitly selected files, not future additions outside that list.
No function executes Git, a compiler, a shell or a network operation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import stat
from typing import Any

from cppulse.contracts import validate
from cppulse.errors import ContractError, InputChanged, IntegrityError

_CHUNK_BYTES = 1024 * 1024
_INVENTORY_LIMIT = "Identity covers this finite selected inventory only; unlisted additions are not observed."


def _string_keys(value: Any) -> None:
    """Reject keys whose implicit JSON string conversion could collide."""
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ContractError("Canonical JSON object keys must be strings")
        for item in value.values():
            _string_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _string_keys(item)


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize finite JSON deterministically as UTF-8, preserving array order.

    This is cppulse's explicit serialization convention, not a claim of full
    RFC 8785 canonicalization. Non-JSON values and nonfinite numbers are errors.
    """
    try:
        _string_keys(value)
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError(f"Identity value is not finite JSON: {exc}") from exc


def digest_json(value: Any) -> str:
    """Return SHA-256 of cppulse's canonical JSON encoding."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _root_directory(root: Path | str) -> Path:
    """Resolve the explicitly selected root, requiring an existing directory."""
    try:
        directory = Path(root).resolve(strict=True)
        if not directory.is_dir():
            raise IntegrityError("Input root must be a directory", path=str(root))
        return directory
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, IntegrityError):
            raise
        raise IntegrityError(f"Input root unavailable: {exc}", path=str(root)) from exc


def _checked_path(root: Path, path: Path | str) -> tuple[Path, str]:
    """Resolve an in-root regular input without following symlink entries."""
    raw = os.fspath(path)
    candidate = Path(path)
    if (
        not raw
        or "\x00" in raw
        or ".." in candidate.parts
        or (os.name != "nt" and "\\" in raw)
        or (not candidate.is_absolute() and PureWindowsPath(raw).drive)
    ):
        raise IntegrityError(
            "Unsafe source path spelling", code="UNSAFE_PATH", path=raw
        )
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise IntegrityError(
            "Input is outside the selected root", code="UNSAFE_PATH", path=raw
        ) from exc
    if not relative.parts:
        raise IntegrityError("Input must be a regular file", path=raw)
    current = root
    try:
        for part in relative.parts:
            current = current / part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise IntegrityError(
                    "Symlink input components are not allowed",
                    code="UNSAFE_PATH",
                    path=relative.as_posix(),
                )
        if not stat.S_ISREG(info.st_mode):
            raise IntegrityError(
                "Input must be a regular file", path=relative.as_posix()
            )
    except (OSError, ValueError) as exc:
        if isinstance(exc, IntegrityError):
            raise
        raise IntegrityError(
            f"Input unavailable: {exc}", path=relative.as_posix()
        ) from exc
    return current, relative.as_posix()


def file_identity(root: Path | str, path: Path | str) -> str:
    """Return a canonical repository-relative POSIX identity for a regular file.

    The caller-selected root itself is resolved. Input entries beneath it may
    not traverse parents or symlinks, including links to an internal alias.
    """
    return _checked_path(_root_directory(root), path)[1]


def _stat_identity(info: os.stat_result) -> tuple[int, ...]:
    """Retain identity and change indicators; reading may legitimately alter atime."""
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _hash_file(root: Path, path: Path | str) -> dict[str, Any]:
    """Hash a regular file and reject observable replacement or mid-read mutation."""
    selected, identity = _checked_path(root, path)
    descriptor: int | None = None
    try:
        before_path = selected.lstat()
        flags = (
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        descriptor = os.open(selected, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or _stat_identity(before) != _stat_identity(
            before_path
        ):
            raise InputChanged("Input changed while opening it", path=identity)
        hasher = hashlib.sha256()
        read_size = 0
        while chunk := os.read(descriptor, _CHUNK_BYTES):
            hasher.update(chunk)
            read_size += len(chunk)
        after = os.fstat(descriptor)
        try:
            current, _ = _checked_path(root, identity)
            current_info = current.lstat()
        except IntegrityError as exc:
            raise InputChanged("Input changed while reading it", path=identity) from exc
        if (
            _stat_identity(before) != _stat_identity(after)
            or _stat_identity(after) != _stat_identity(current_info)
            or read_size != after.st_size
        ):
            raise InputChanged("Input changed while reading it", path=identity)
        return {"path": identity, "sha256": hasher.hexdigest(), "size_bytes": read_size}
    except FileNotFoundError as exc:
        raise InputChanged(
            "Input changed while opening or reading it", path=identity
        ) from exc
    except OSError as exc:
        raise IntegrityError(f"Could not read input: {exc}", path=identity) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def snapshot_inputs(
    root: Path | str,
    files: Iterable[Path | str],
    kind: str = "application",
    inventory_complete: bool = False,
    revision: str | None = None,
    dirty: bool | None = None,
) -> dict[str, Any]:
    """Snapshot a finite selected inventory and validate its source v2 contract.

    Args:
        root: Explicitly selected source root; no Git discovery is performed.
        files: Existing regular inputs, supplied relative to root or absolute.
        kind: application, library or header-only.
        inventory_complete: Caller assertion for this finite inventory only.
        revision: Optional caller-supplied revision metadata, excluded from digest.
        dirty: Optional caller-supplied dirty metadata, excluded from digest.

    A second content verification detects changes while other inputs were read.
    This is not a filesystem transaction: collection must verify again after
    execution. New unlisted inputs are deliberately not discovered here.
    """
    directory = _root_directory(root)
    records = []
    seen = set()
    for path in files:
        identity = _checked_path(directory, path)[1]
        key = os.path.normcase(identity)
        if key in seen:
            raise ContractError(
                f"Duplicate selected source path: {identity}",
                code="DUPLICATE_ID",
                path=identity,
            )
        seen.add(key)
        records.append(_hash_file(directory, identity))
    records.sort(key=lambda entry: entry["path"])
    projection = {
        "kind": kind,
        "files": records,
        "inventory_complete": inventory_complete,
    }
    limitations = [_INVENTORY_LIMIT]
    if not inventory_complete:
        limitations.append(
            "Completeness of the selected inventory has not been asserted."
        )
    if not records:
        limitations.append("No input files were selected.")
    document = {
        "version": "2.0.0",
        "digest": digest_json(projection),
        **projection,
        "limitations": limitations,
    }
    if revision is not None:
        document["revision"] = revision
    if dirty is not None:
        document["dirty"] = dirty
    validate("source", document)
    errors = verify_inputs(directory, document)
    if errors:
        raise InputChanged(
            "Selected inputs changed during snapshot: " + "; ".join(errors)
        )
    return document


def verify_inputs(root: Path | str, snapshot: dict[str, Any]) -> list[str]:
    """Return listed-input discrepancies; validate the snapshot before reading files.

    Replacements with identical bytes remain content-equivalent once stable.
    New unlisted additions require a fresh discovery inventory, not this check.
    """
    validate("source", snapshot)
    try:
        directory = _root_directory(root)
    except IntegrityError as exc:
        return [str(exc)]
    errors = []
    for expected in snapshot["files"]:
        identity = expected["path"]
        try:
            observed = _hash_file(directory, identity)
        except (IntegrityError, InputChanged) as exc:
            errors.append(f"{identity}: {exc}")
            continue
        if (
            observed["sha256"] != expected["sha256"]
            or observed["size_bytes"] != expected["size_bytes"]
        ):
            errors.append(f"{identity}: content differs from the selected snapshot")
    return errors


def context_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a validated context v2 identity without mutating supplied compile facts.

    Run IDs/timestamps are not context fields and are rejected by the contract.
    A supplied context ID is retained; otherwise it is derived from the digest.
    """
    supplied = deepcopy(dict(payload))
    for key in ("run_id", "timestamp", "generated_at", "started_at", "finished_at"):
        if key in supplied:
            raise ContractError(
                "Run metadata does not belong to a context identity", path="/" + key
            )
    projection = {
        key: value
        for key, value in supplied.items()
        if key not in {"version", "id", "digest", "limitations"}
    }
    digest = digest_json(projection)
    document = {
        "version": "2.0.0",
        "id": supplied.get("id", "ctx-" + digest),
        "digest": digest,
        **projection,
        "limitations": supplied.get("limitations", []),
    }
    validate("context", document)
    return document


def hash_artifact(
    path: Path | str,
    artifact_id: str,
    destination: str,
    media_type: str,
) -> dict[str, Any]:
    """Identify selected artifact bytes without copying or publishing them.

    destination is a canonical relative run path, independently validated by
    the artifact contract. The explicitly selected source file cannot be a
    symlink. Its parent is resolved as the chosen source directory.
    """
    record = {
        "id": artifact_id,
        "path": destination,
        "sha256": "0" * 64,
        "size_bytes": 0,
        "media_type": media_type,
    }
    validate("artifact", record)
    source = Path(path)
    if ".." in source.parts:
        raise IntegrityError(
            "Artifact source must not traverse parents",
            code="UNSAFE_PATH",
            path=str(path),
        )
    parent = _root_directory(source.parent)
    content = _hash_file(parent, source.name)
    record.update(sha256=content["sha256"], size_bytes=content["size_bytes"])
    validate("artifact", record)
    return record
