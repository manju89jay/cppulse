"""Bounded selected namespace inventory, a prerequisite for retained image layers.

Inventorying live files does not make their namespace immutable. This module
does not execute containers, produce native receipts or authorize cache reuse.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import PurePosixPath
import stat
from typing import Any

from cppulse.contracts.frozen_input import validate_frozen_input
from cppulse.errors import ContractError, InputChanged


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _open_root(path: str) -> int:
    """Walk every selected root component without following host symlinks."""
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in PurePosixPath(path).parts[1:]:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def inventory_frozen_inputs(request: dict[str, Any]) -> list[dict[str, Any]]:
    """Hash a finite selected namespace using checked descriptors and bounds.

    Reject symlinks, devices, mount crossings and hardlinked files in this first
    producer profile. No output artifact or mutation is performed. A successful
    result identifies observed selected bytes, not a simultaneous host snapshot.
    """
    validate_frozen_input("request", request)
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ContractError("Frozen namespace producer requires POSIX nofollow")
    rows: list[dict[str, Any]] = []
    total = 0
    limits = request["limits"]

    def names(descriptor: int) -> list[str]:
        selected: list[str] = []
        with os.scandir(descriptor) as children:
            for child in children:
                if len(selected) >= limits["max_entries"]:
                    raise ContractError("Selected directory exceeds entry boundary")
                selected.append(child.name)
        return sorted(selected)

    def visit(
        parent: int,
        name: str | None,
        source: str,
        relative: PurePosixPath,
        container: PurePosixPath,
        device: int,
        depth: int,
    ) -> None:
        nonlocal total
        if depth > 64 or len(rows) >= limits["max_entries"]:
            raise ContractError("Selected namespace exceeds traversal boundary")
        original = (
            os.fstat(parent)
            if name is None
            else os.stat(name, dir_fd=parent, follow_symlinks=False)
        )
        directory = stat.S_ISDIR(original.st_mode)
        if original.st_dev != device or not (
            directory or stat.S_ISREG(original.st_mode)
        ):
            raise ContractError("Unsupported mount, symlink or special input")
        if not directory and original.st_nlink != 1:
            raise ContractError("Hardlinked input unsupported in finite profile")
        descriptor = (
            os.dup(parent)
            if name is None
            else os.open(
                name,
                os.O_RDONLY
                | os.O_NOFOLLOW
                | os.O_NONBLOCK
                | (os.O_DIRECTORY if directory else 0),
                dir_fd=parent,
            )
        )
        try:
            before = os.fstat(descriptor)
            if _identity(before) != _identity(original):
                raise InputChanged("Selected input changed during descriptor selection")
            if (
                stat.S_IMODE(before.st_mode) > 0o777
                or not 0 <= before.st_mtime_ns <= 2**63 - 1
            ):
                raise ContractError("Unsupported input permission bits or timestamp")
            if any(
                len(value.encode("utf-8")) > 4096
                for value in (str(container), str(relative), source)
            ):
                raise ContractError("Selected namespace path exceeds byte boundary")
            row: dict[str, Any] = {
                "path": str(container),
                "kind": "directory" if directory else "regular",
                "mode": stat.S_IMODE(before.st_mode),
                "mtime_ns": before.st_mtime_ns,
                "source_root": source,
                "source_relative": str(relative),
                "content": None,
                "target": None,
            }
            rows.append(row)
            if directory:
                original_names = names(descriptor)
                for child in original_names:
                    if not child or child in {".", ".."} or "\x00" in child:
                        raise ContractError("Invalid selected namespace name")
                    try:
                        child.encode("utf-8", errors="strict")
                    except UnicodeError as exc:
                        raise ContractError("Non-UTF8 selected namespace") from exc
                    visit(
                        descriptor,
                        child,
                        source,
                        relative / child,
                        container / child,
                        device,
                        depth + 1,
                    )
                if names(descriptor) != original_names:
                    raise InputChanged("Selected directory entries changed")
            else:
                if before.st_size > limits["max_payload_bytes"] - total:
                    raise ContractError("Selected payload exceeds byte boundary")
                digest = hashlib.sha256()
                size = 0
                while chunk := os.read(descriptor, 1024 * 1024):
                    size += len(chunk)
                    if (
                        size > before.st_size
                        or total + size > limits["max_payload_bytes"]
                    ):
                        raise InputChanged("Selected input grew during capture")
                    digest.update(chunk)
                if size != before.st_size:
                    raise InputChanged("Selected input shrank during capture")
                total += size
                row["content"] = {"sha256": digest.hexdigest(), "size_bytes": size}
            if _identity(os.fstat(descriptor)) != _identity(before):
                raise InputChanged("Selected input changed during inventory")
            if name is not None and _identity(
                os.stat(name, dir_fd=parent, follow_symlinks=False)
            ) != _identity(before):
                raise InputChanged("Selected input pathname changed")
        finally:
            os.close(descriptor)

    try:
        for mapping in request["path_map"]:
            descriptor = _open_root(mapping["source_root"])
            try:
                visit(
                    descriptor,
                    None,
                    mapping["source_root"],
                    PurePosixPath("."),
                    PurePosixPath(mapping["container_root"]),
                    os.fstat(descriptor).st_dev,
                    0,
                )
            finally:
                os.close(descriptor)
    except OSError as exc:
        raise InputChanged("Selected input namespace unavailable or changed") from exc
    return sorted(rows, key=lambda row: row["path"])
