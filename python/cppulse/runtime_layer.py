"""Retain declared runtime files and checked captured inputs without raw staging."""
from __future__ import annotations
from contextlib import ExitStack
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import tarfile
from typing import Any
from cppulse.errors import ContractError, InputChanged
from cppulse.frozen_input import _identity, _open_root
from cppulse.frozen_layer import (
    _check_parent_path,
    _format_ns,
    _publish_compressed_layer,
    verify_archive,
    verify_frozen_layer,
)
from cppulse.identities import canonical_json_bytes
from cppulse.contracts.runtime_input import validate_namespace, validate_runtime_layer
from cppulse.runtime_input import load_runtime_manifest


def _copy(value):
    return json.loads(canonical_json_bytes(value))


class _Guard:
    def __init__(self, path: Path, stack: ExitStack):
        self.path = path.absolute()
        self.parent = _open_root(str(self.path.parent))
        stack.callback(os.close, self.parent)
        self.parent_before = os.fstat(self.parent)
        self.fd = os.open(
            self.path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=self.parent,
        )
        stack.callback(os.close, self.fd)
        self.before = os.fstat(self.fd)
        if not stat.S_ISREG(self.before.st_mode):
            raise ContractError("Selected input is not regular")

    def check(self):
        if _identity(os.fstat(self.fd)) != _identity(self.before) or _identity(
            os.stat(self.path.name, dir_fd=self.parent, follow_symlinks=False)
        ) != _identity(self.before):
            raise InputChanged("Selected runtime/capture input changed")
        _check_parent_path(self.path.parent, self.parent_before)


class _FDReader:
    def __init__(self, descriptor):
        self.descriptor = descriptor

    def read(self, count):
        chunks = []
        remaining = count
        while remaining:
            chunk = os.read(self.descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


class _Reader:
    def __init__(self, stream, expected):
        self.stream = stream
        self.expected = expected
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, count):
        data = self.stream.read(count)
        self.size += len(data)
        if self.size > self.expected["size_bytes"]:
            raise InputChanged("Runtime source grew")
        self.digest.update(data)
        return data

    def check(self):
        if (
            self.size != self.expected["size_bytes"]
            or self.digest.hexdigest() != self.expected["sha256"]
        ):
            raise InputChanged("Runtime stream differs from declared bytes")


class _HashWriter:
    def __init__(self, stream, maximum):
        self.stream = stream
        self.maximum = maximum
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, data):
        if self.size + len(data) > self.maximum:
            raise ContractError("Runtime archive stream exceeds bound")
        count = self.stream.write(data)
        if count != len(data):
            raise OSError("Short runtime archive write")
        self.size += count
        self.digest.update(data)
        return count

    def flush(self):
        self.stream.flush()

    def descriptor(self):
        return {"sha256": self.digest.hexdigest(), "size_bytes": self.size}


def _seal_input(item, stack):
    capture = item["capture"]
    path = Path(item["path"])
    verify_frozen_layer(capture, path, request=item["request"])
    guard = _Guard(path, stack)
    if guard.before.st_size != capture["compressed_layer"]["size_bytes"]:
        raise InputChanged("Input capture size changed")
    fd = os.memfd_create(
        "cppulse-retained-capture", os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC
    )
    stack.callback(os.close, fd)
    digest = hashlib.sha256()
    size = 0
    while data := os.read(guard.fd, 1024 * 1024):
        size += len(data)
        if size > capture["compressed_layer"]["size_bytes"]:
            raise InputChanged("Capture grew during sealing")
        digest.update(data)
        offset = 0
        while offset < len(data):
            count = os.write(fd, data[offset:])
            if count <= 0:
                raise OSError("Short capture seal write")
            offset += count
    if (
        size != capture["compressed_layer"]["size_bytes"]
        or digest.hexdigest() != capture["compressed_layer"]["sha256"]
    ):
        raise InputChanged("Capture changed during sealing")
    guard.check()
    fcntl.fcntl(
        fd,
        getattr(fcntl, "F_ADD_SEALS", 1033),
        0x000F,  # Linux UAPI: WRITE|SHRINK|GROW|SEAL.
    )
    if fcntl.fcntl(fd, getattr(fcntl, "F_GET_SEALS", 1034)) & 0x000F != 0x000F:
        raise ContractError("Required Linux capture seals were not applied")
    os.lseek(fd, 0, os.SEEK_SET)
    source = stack.enter_context(os.fdopen(os.dup(fd), "rb"))
    archive = stack.enter_context(tarfile.open(fileobj=source, mode="r:gz"))
    # Sealed bytes equal the already strictly verified gzip/PAX artifact.
    members = archive.getmembers()
    if len(members) != len(capture["entries"]):
        raise ContractError("Sealed capture member count differs")
    return (
        guard,
        archive,
        {row["path"]: member for row, member in zip(capture["entries"], members)},
    )


def retain_runtime_layer(
    manifest: dict[str, Any],
    inputs: list[dict[str, Any]],
    directories: list[dict[str, Any]],
    destination: Path,
) -> dict[str, Any]:
    """Publish a historical byte snapshot, never image/execution/cache proof."""
    manifest = load_runtime_manifest(canonical_json_bytes(manifest))
    directories = _copy(directories)
    inputs = [
        {
            "capture": _copy(item["capture"]),
            "request": _copy(item["request"]),
            "path": str(item["path"]),
        }
        for item in inputs
    ]
    namespace = validate_namespace(
        manifest, [item["capture"] for item in inputs], directories
    )
    if (
        sum(item["capture"]["compressed_layer"]["size_bytes"] for item in inputs)
        > 64 * 1024**2
    ):
        raise ContractError("Initial profile limits sealed compressed inputs to64MiB")
    destination = Path(destination).absolute()
    if destination.parent.resolve() != destination.parent:
        raise ContractError("Output directory is not canonical")
    for item in inputs:
        for mapping in item["request"]["path_map"]:
            root = Path(mapping["source_root"])
            if destination == root or root in destination.parents:
                raise ContractError("Output is inside selected input source")
    entries = namespace["entries"]
    runtime = {row["container_path"]: row for row in manifest["files"]}
    maximum = namespace["payload_bytes"] + len(entries) * 8192 + 10240
    with ExitStack() as stack:
        parent = _open_root(str(destination.parent))
        stack.callback(os.close, parent)
        parent_before = os.fstat(parent)
        if (
            parent_before.st_uid != os.getuid()
            or stat.S_IMODE(parent_before.st_mode) & 0o077
        ):
            raise ContractError("Output directory must be private and owned")
        try:
            os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("Runtime output exists")
        guards = []
        captured = {}
        for item in inputs:
            guard, archive, members = _seal_input(item, stack)
            guards.append(guard)
            for path, member in members.items():
                captured[path] = (archive, member)
        partial = destination.with_name(destination.name + ".partial")
        fd = os.open(
            partial.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent,
        )
        with os.fdopen(fd, "wb") as output:
            compressed_writer = _HashWriter(output, maximum + maximum // 1000 + 1024)
            with gzip.GzipFile(
                filename="", mode="wb", mtime=0, fileobj=compressed_writer
            ) as compressed:
                raw_writer = _HashWriter(compressed, maximum)
                with tarfile.open(
                    mode="w|", fileobj=raw_writer, format=tarfile.PAX_FORMAT
                ) as archive:
                    for row in entries:
                        info = tarfile.TarInfo(row["path"].lstrip("/"))
                        info.uid = info.gid = 1000
                        info.mode = row["mode"]
                        info.mtime = row["mtime_ns"] // 10**9
                        info.pax_headers = {"mtime": _format_ns(row["mtime_ns"])}
                        if row["kind"] == "directory":
                            info.type = tarfile.DIRTYPE
                            archive.addfile(info)
                            continue
                        info.size = row["content"]["size_bytes"]
                        if row["path"] in runtime:
                            selected = runtime[row["path"]]
                            guard = _Guard(Path(selected["source_path"]), stack)
                            guards.append(guard)
                            before = guard.before
                            if (
                                before.st_nlink != 1
                                or before.st_size != info.size
                                or before.st_mtime_ns != row["mtime_ns"]
                                or stat.S_IMODE(before.st_mode) != row["mode"]
                            ):
                                raise InputChanged("Runtime source identity differs")
                            source = _FDReader(guard.fd)
                        else:
                            selected_archive, member = captured[row["path"]]
                            source = stack.enter_context(
                                selected_archive.extractfile(member)
                            )
                        reader = _Reader(source, row["content"])
                        archive.addfile(info, reader)
                        reader.check()
            output.flush()
            os.fsync(output.fileno())
        for guard in guards:
            guard.check()
        archive_doc = {
            "version": "0.1.0",
            "cache_eligible": False,
            "closure": "unqualified",
            "entries": [
                {
                    key: row[key]
                    for key in ("path", "kind", "mode", "mtime_ns", "content")
                }
                for row in entries
            ],
            "raw_layer": raw_writer.descriptor(),
            "compressed_layer": compressed_writer.descriptor(),
            "compression": "gzip",
            "ownership": {"uid": 1000, "gid": 1000},
        }
        verify_archive(archive_doc, partial)
        for guard in guards:
            guard.check()
        _publish_compressed_layer(
            archive_doc, destination, partial, parent, parent_before
        )
    result = {
        "version": "0.1.0",
        "cache_eligible": False,
        "closure": "unqualified",
        "native_executed": False,
        "runtime_manifest_sha256": hashlib.sha256(
            canonical_json_bytes(manifest)
        ).hexdigest(),
        "input_capture_sha256": [
            hashlib.sha256(canonical_json_bytes(item["capture"])).hexdigest()
            for item in inputs
        ],
        "semantic_namespace_sha256": namespace["semantic_namespace_sha256"],
        "archive": archive_doc,
        "qualification": "Retained declared bytes only; no ELF readiness, image/native execution or cache qualification.",
    }
    validate_runtime_layer(result)
    return result
