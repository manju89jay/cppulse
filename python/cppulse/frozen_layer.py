"""Retain the same checked bytes hashed into a finite gzip-compressed tar layer.

No Docker/image operations or cache qualification are performed. Partial output
is deliberately preserved on failure; only a successful return describes a layer.
"""

from __future__ import annotations

import gzip
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import uuid
import zlib
from typing import Any

from cppulse.contracts.frozen_input import validate_frozen_input
from cppulse.errors import ContractError, InputChanged
from cppulse.frozen_input import _identity, _open_root, inventory_frozen_inputs
from cppulse.identities import canonical_json_bytes


def _check_parent_path(path: Path, expected: os.stat_result) -> None:
    """Bind the selected current parent path as well as its held descriptor."""
    current = _open_root(str(path))
    try:
        value = os.fstat(current)
        if (value.st_dev, value.st_ino, value.st_mode, value.st_uid) != (
            expected.st_dev,
            expected.st_ino,
            expected.st_mode,
            expected.st_uid,
        ):
            raise InputChanged("Selected layer parent pathname changed")
    finally:
        os.close(current)


def _format_ns(value: int) -> str:
    seconds, nanoseconds = divmod(value, 10**9)
    return str(seconds) + "." + str(nanoseconds).zfill(9)


def _capture_layer(
    request: dict[str, Any], destination: Path, output_parent: int
) -> dict[str, Any]:
    """Retain bounded selected namespace bytes without raw host staging.

    The selected live namespace is checked before and after capture; the result
    binds actual archive bytes to retained metadata. This does not prove a
    simultaneous host snapshot or any runtime/non-filesystem input closure.
    """
    validate_frozen_input("request", request)
    destination = Path(destination).absolute()
    if destination.parent.resolve() != destination.parent:
        raise ContractError("Layer output parent must be canonical and existing")
    roots = [Path(row["source_root"]) for row in request["path_map"]]
    if any(destination == root or root in destination.parents for root in roots):
        raise ContractError("Layer output cannot be inside selected inputs")
    root_guards = {}
    for root in roots:
        fd = _open_root(str(root))
        try:
            root_guards[str(root)] = _identity(os.fstat(fd))
        finally:
            os.close(fd)
    entries = inventory_frozen_inputs(request)
    guards = {}
    for row in entries:
        if row["kind"] != "directory":
            continue
        path = str(Path(row["source_root"]) / row["source_relative"])
        fd = _open_root(path)
        try:
            value = os.fstat(fd)
            if (
                value.st_mtime_ns != row["mtime_ns"]
                or stat.S_IMODE(value.st_mode) != row["mode"]
            ):
                raise InputChanged("Selected directory metadata changed")
            expected = sorted(
                PurePosixPath(other["path"]).name
                for other in entries
                if PurePosixPath(other["path"]).parent == PurePosixPath(row["path"])
            )
            with os.scandir(fd) as children:
                actual = []
                for child in children:
                    if len(actual) >= request["limits"]["max_entries"]:
                        raise ContractError("Layer directory exceeds entry boundary")
                    actual.append(child.name)
            if sorted(actual) != expected:
                raise InputChanged("Selected directory membership changed")
            guards[path] = _identity(value)
        finally:
            os.close(fd)
    if any(guards.get(root) != value for root, value in root_guards.items()):
        raise InputChanged("Selected root was replaced before capture")
    maximum = (
        request["limits"]["max_payload_bytes"]
        + request["limits"]["max_entries"] * 8192
        + 10240
    )
    raw_digest, compressed_digest = hashlib.sha256(), hashlib.sha256()
    raw_count = compressed_count = 0

    class CompressedWriter:
        def __init__(self, stream):
            self.stream = stream

        def write(self, data):
            nonlocal compressed_count
            compressed_count += len(data)
            if compressed_count > maximum + maximum // 1000 + 1024:
                raise ContractError("Compressed layer exceeds byte boundary")
            compressed_digest.update(data)
            return self.stream.write(data)

        def flush(self):
            self.stream.flush()

    class LayerWriter:
        def __init__(self, stream):
            self.stream = stream

        def write(self, data):
            nonlocal raw_count
            raw_count += len(data)
            if raw_count > maximum:
                raise ContractError("Raw layer exceeds byte boundary")
            raw_digest.update(data)
            return self.stream.write(data)

    class CheckedReader:
        def __init__(self, descriptor):
            self.descriptor = descriptor
            self.digest = hashlib.sha256()
            self.size = 0

        def read(self, count):
            data = os.read(self.descriptor, count)
            self.digest.update(data)
            self.size += len(data)
            return data

    with os.fdopen(
        os.open(
            destination.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=output_parent,
        ),
        "wb",
    ) as output:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=CompressedWriter(output), mtime=0
        ) as compressed:
            with tarfile.open(
                mode="w|", fileobj=LayerWriter(compressed), format=tarfile.PAX_FORMAT
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
                    source = Path(row["source_root"]) / row["source_relative"]
                    parent = _open_root(str(source.parent))
                    fd = None
                    try:
                        fd = os.open(
                            source.name,
                            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                            dir_fd=parent,
                        )
                        before = os.fstat(fd)
                        if (
                            not stat.S_ISREG(before.st_mode)
                            or before.st_nlink != 1
                            or before.st_size != row["content"]["size_bytes"]
                            or before.st_mtime_ns != row["mtime_ns"]
                            or stat.S_IMODE(before.st_mode) != row["mode"]
                        ):
                            raise InputChanged(
                                "Selected file changed before layer capture"
                            )
                        info.size = row["content"]["size_bytes"]
                        reader = CheckedReader(fd)
                        archive.addfile(info, reader)
                        if (
                            reader.size != info.size
                            or reader.digest.hexdigest() != row["content"]["sha256"]
                        ):
                            raise InputChanged(
                                "Archived bytes differ from selected bytes"
                            )
                        if _identity(os.fstat(fd)) != _identity(before) or _identity(
                            os.stat(source.name, dir_fd=parent, follow_symlinks=False)
                        ) != _identity(before):
                            raise InputChanged(
                                "Selected file changed during layer capture"
                            )
                    finally:
                        if fd is not None:
                            os.close(fd)
                        os.close(parent)
        output.flush()
        os.fsync(output.fileno())
    for path, before in guards.items():
        fd = _open_root(path)
        try:
            if _identity(os.fstat(fd)) != before:
                raise InputChanged(
                    "Selected directory/root changed during layer capture"
                )
        finally:
            os.close(fd)
    if inventory_frozen_inputs(request) != entries:
        raise InputChanged("Selected namespace changed during layer capture")
    result = {
        "version": "0.1.0",
        "state": "retained_verified",
        "cache_eligible": False,
        "closure": "unqualified",
        "request_sha256": hashlib.sha256(canonical_json_bytes(request)).hexdigest(),
        "entries": entries,
        "raw_layer": {"sha256": raw_digest.hexdigest(), "size_bytes": raw_count},
        "compressed_layer": {
            "sha256": compressed_digest.hexdigest(),
            "size_bytes": compressed_count,
        },
        "compression": "gzip",
        "ownership": {"uid": 1000, "gid": 1000},
        "qualification": "Retained selected filesystem bytes only; no image/runtime or non-filesystem closure.",
    }

    validate_frozen_input("capture", result)
    return result


def retain_frozen_layer(request: dict[str, Any], destination: Path) -> dict[str, Any]:
    """Publish one verified layer exclusively from a retained partial artifact.

    The caller must select an owned private directory outside all input roots.
    Failed capture keeps only the .partial artifact; a final name is linked
    exclusively after content/namespace validation and checked path binding.
    """
    validate_frozen_input("request", request)
    destination = Path(destination).absolute()
    if destination.parent.resolve() != destination.parent:
        raise ContractError("Layer output parent must be canonical")
    if any(
        Path(row["source_root"]) in destination.parents for row in request["path_map"]
    ):
        raise ContractError("Layer output cannot be inside selected inputs")
    parent = _open_root(str(destination.parent))
    try:
        parent_stat = os.fstat(parent)
        if (
            parent_stat.st_uid != os.getuid()
            or stat.S_IMODE(parent_stat.st_mode) & 0o077
        ):
            raise ContractError("Layer output directory must be owned and private")
        try:
            os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("Layer destination already exists")
        partial = destination.with_name(destination.name + ".partial")
        result = _capture_layer(request, partial, parent)
        return _publish_compressed_layer(
            result, destination, partial, parent, parent_stat
        )
    finally:
        os.close(parent)


def _publish_compressed_layer(
    result: dict[str, Any],
    destination: Path,
    partial: Path,
    parent: int,
    parent_stat: os.stat_result,
) -> dict[str, Any]:
    """Exclusively publish a previously checked compressed artifact by FD."""
    descriptor = os.open(
        partial.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size != result["compressed_layer"]["size_bytes"]
        ):
            raise InputChanged("Retained partial artifact changed")
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            size += len(chunk)
            if size > before.st_size:
                raise InputChanged("Retained partial artifact grew")
            digest.update(chunk)
        if (
            digest.hexdigest() != result["compressed_layer"]["sha256"]
            or size != before.st_size
            or _identity(os.fstat(descriptor)) != _identity(before)
        ):
            raise InputChanged("Retained partial artifact bytes changed")
        if _identity(
            os.stat(partial.name, dir_fd=parent, follow_symlinks=False)
        ) != _identity(before):
            raise InputChanged("Retained partial artifact pathname changed")
        current_parent = _open_root(str(destination.parent))
        try:
            current = os.fstat(current_parent)
            if (current.st_dev, current.st_ino) != (
                parent_stat.st_dev,
                parent_stat.st_ino,
            ):
                raise InputChanged("Layer output directory was replaced")
        finally:
            os.close(current_parent)
        if not os.path.exists("/proc/self/fd/" + str(descriptor)):
            raise ContractError(
                "Descriptor publication requires supported Linux procfs"
            )
        published = False
        try:
            os.link(
                "/proc/self/fd/" + str(descriptor),
                destination.name,
                dst_dir_fd=parent,
                follow_symlinks=True,
            )
            published = True
            after = os.fstat(descriptor)
            final = os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
            if (after.st_dev, after.st_ino, after.st_mode, after.st_nlink) != (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_nlink + 1,
            ) or (final.st_dev, final.st_ino, final.st_mode, final.st_nlink) != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_nlink,
            ):
                raise InputChanged("Layer publication changed descriptor identity")
            if (
                os.stat(partial.name, dir_fd=parent, follow_symlinks=False).st_ino
                != before.st_ino
            ):
                raise InputChanged("Retained witness pathname changed")
            # Creating a hardlink changes ctime/nlink legitimately. It must
            # not hide a same-inode content write at the publication boundary.
            linked = os.fstat(descriptor)
            if (linked.st_size, linked.st_mtime_ns) != (
                before.st_size,
                before.st_mtime_ns,
            ):
                raise InputChanged("Layer bytes changed during publication")
            os.lseek(descriptor, 0, os.SEEK_SET)
            digest = hashlib.sha256()
            size = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                size += len(chunk)
                if size > result["compressed_layer"]["size_bytes"]:
                    raise InputChanged("Published layer grew")
                digest.update(chunk)
            if (
                size != result["compressed_layer"]["size_bytes"]
                or digest.hexdigest() != result["compressed_layer"]["sha256"]
                or _identity(os.fstat(descriptor)) != _identity(linked)
            ):
                raise InputChanged("Published layer bytes differ")
            os.fsync(parent)
            _check_parent_path(destination.parent, parent_stat)
            if _identity(
                os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
            ) != _identity(linked):
                raise InputChanged("Published layer pathname changed")
            return result
        except BaseException:
            if published:
                final = os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
                if (final.st_dev, final.st_ino) != (before.st_dev, before.st_ino):
                    raise InputChanged(
                        "Publication state uncertain: foreign final pathname"
                    )
                try:
                    witness = os.stat(
                        partial.name, dir_fd=parent, follow_symlinks=False
                    )
                except FileNotFoundError:
                    witness = None
                if witness is None or (witness.st_dev, witness.st_ino) != (
                    before.st_dev,
                    before.st_ino,
                ):
                    recovery_name = (
                        partial.name + "." + uuid.uuid4().hex + ".preserved-witness"
                    )
                    os.link(
                        "/proc/self/fd/" + str(descriptor),
                        recovery_name,
                        dst_dir_fd=parent,
                        follow_symlinks=True,
                    )
                os.unlink(destination.name, dir_fd=parent)
                os.fsync(parent)
            raise
    finally:
        os.close(descriptor)


def verify_frozen_layer(
    capture: dict[str, Any], path: Path, *, request: dict[str, Any]
) -> None:
    """Independently verify bounded archive bytes and every retained entry.

    Supports only this producer's regular files, directories and small PAX
    path/mtime records. No extraction, native execution or closure is implied.
    """
    validate_frozen_input("request", request)
    validate_frozen_input("capture", capture)
    if (
        capture["request_sha256"]
        != hashlib.sha256(canonical_json_bytes(request)).hexdigest()
    ):
        raise ContractError("Retained capture changes original selected request")
    entries = capture["entries"]
    roots = {
        row["source_root"]: PurePosixPath(row["container_root"])
        for row in request["path_map"]
    }
    if len(entries) > request["limits"]["max_entries"]:
        raise ContractError("Retained namespace exceeds selected entry budget")
    if {row["path"] for row in entries if row["source_relative"] == "."} != {
        str(root) for root in roots.values()
    }:
        raise ContractError("Retained namespace omits selected roots")
    selected = {row["path"]: row for row in entries}
    for row in entries:
        root = roots.get(row["source_root"])
        if root is None or str(root / row["source_relative"]) != row["path"]:
            raise ContractError("Retained namespace changes original source mapping")
        for parent in PurePosixPath(row["path"]).parents:
            if parent == root.parent:
                break
            if (
                str(parent) not in selected
                or selected[str(parent)]["kind"] != "directory"
            ):
                raise ContractError("Retained namespace omits ancestor directory")
    if (
        sum(row["content"]["size_bytes"] for row in entries if row["content"])
        > request["limits"]["max_payload_bytes"]
    ):
        raise ContractError("Retained payload exceeds selected request budget")
    fields = (
        "version",
        "cache_eligible",
        "closure",
        "raw_layer",
        "compressed_layer",
        "compression",
        "ownership",
    )
    archive = {key: capture[key] for key in fields}
    archive["entries"] = [
        {key: row[key] for key in ("path", "kind", "mode", "mtime_ns", "content")}
        for row in entries
    ]
    verify_archive(archive, path)


def verify_archive(capture: dict[str, Any], path: Path) -> None:
    """Verify only archive bytes/metadata; no source or execution proof inferred."""
    validate_frozen_input("archive", capture)
    entries = capture["entries"]
    payload = sum(row["content"]["size_bytes"] for row in entries if row["content"])
    if payload > 512 * 1024**2:
        raise ContractError("Retained payload exceeds supported verification budget")
    maximum = payload + len(entries) * 8192 + 10240
    if (
        capture["raw_layer"]["size_bytes"] > maximum
        or capture["compressed_layer"]["size_bytes"] > maximum + maximum // 1000 + 1024
    ):
        raise ContractError("Retained archive exceeds supported overhead boundary")
    parent = _open_root(str(Path(path).absolute().parent))
    parent_before = os.fstat(parent)
    descriptor = None
    try:
        descriptor = os.open(
            Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size != capture["compressed_layer"]["size_bytes"]
        ):
            raise ContractError("Retained compressed artifact size/type mismatch")
        digest = hashlib.sha256()
        size = 0
        while data := os.read(descriptor, 1024 * 1024):
            size += len(data)
            if size > before.st_size:
                raise InputChanged("Retained compressed artifact grew")
            digest.update(data)
        if (
            size != before.st_size
            or digest.hexdigest() != capture["compressed_layer"]["sha256"]
        ):
            raise ContractError("Retained compressed artifact hash mismatch")
        os.lseek(descriptor, 0, os.SEEK_SET)
        # Dup shares position but keeps ownership of the caller's checked fd.
        with os.fdopen(os.dup(descriptor), "rb") as source:
            with gzip.GzipFile(fileobj=source, mode="rb") as raw:
                raw_digest = hashlib.sha256()
                raw_size = 0

                def read(count):
                    nonlocal raw_size
                    if count < 0 or count > 1024 * 1024:
                        raise ContractError("Unsupported archive read boundary")
                    data = raw.read(count)
                    raw_size += len(data)
                    if raw_size > capture["raw_layer"]["size_bytes"]:
                        raise ContractError(
                            "Expanded archive exceeds selected raw size"
                        )
                    raw_digest.update(data)
                    return data

                def exact(count):
                    data = read(count)
                    if len(data) != count:
                        raise ContractError("Truncated retained archive")
                    return data

                def padding(size):
                    if any(exact((-size) % 512)):
                        raise ContractError("Nonzero archive padding")

                def pax(body):
                    result = {}
                    offset = 0
                    while offset < len(body):
                        space = body.find(b" ", offset, offset + 7)
                        digits = body[offset:space] if space != -1 else b""
                        if not digits or not digits.isdigit() or len(digits) > 5:
                            raise ContractError("Invalid PAX record length")
                        length = int(digits)
                        if (
                            str(length).encode() != digits
                            or length <= len(digits) + 3
                            or offset + length > len(body)
                        ):
                            raise ContractError("Invalid PAX record boundary")
                        record = body[space + 1 : offset + length]
                        if not record.endswith(b"\n") or b"=" not in record:
                            raise ContractError("Invalid PAX record")
                        key, value = record[:-1].split(b"=", 1)
                        if key not in {b"path", b"mtime"} or key.decode() in result:
                            raise ContractError("Unsupported or duplicate PAX field")
                        result[key.decode()] = value.decode("utf-8", errors="strict")
                        offset += length
                    return result

                for expected in entries:
                    header = tarfile.TarInfo.frombuf(exact(512), "utf-8", "strict")
                    if header.type != tarfile.XHDTYPE or header.size > 16384:
                        raise ContractError("Expected finite per-entry PAX metadata")
                    metadata = pax(exact(header.size))
                    padding(header.size)
                    member = tarfile.TarInfo.frombuf(exact(512), "utf-8", "strict")
                    expected_type = (
                        tarfile.DIRTYPE
                        if expected["kind"] == "directory"
                        else tarfile.REGTYPE
                    )
                    if (
                        expected["kind"] not in {"directory", "regular"}
                        or member.type != expected_type
                    ):
                        raise ContractError("Unsupported archive member type")
                    name = metadata.get("path", member.name)
                    expected_name = expected["path"].lstrip("/")
                    supported_names = (
                        {expected_name, expected_name + "/"}
                        if expected["kind"] == "directory"
                        else {expected_name}
                    )
                    if name not in supported_names or metadata.get(
                        "mtime"
                    ) != _format_ns(expected["mtime_ns"]):
                        raise ContractError("Archive path or exact timestamp differs")
                    if (
                        member.mode != expected["mode"]
                        or member.uid != 1000
                        or member.gid != 1000
                        or member.uname
                        or member.gname
                        or member.linkname
                    ):
                        raise ContractError(
                            "Archive ownership/mode/link metadata differs"
                        )
                    expected_size = (
                        expected["content"]["size_bytes"] if expected["content"] else 0
                    )
                    if member.size != expected_size:
                        raise ContractError("Archive member size differs")
                    content = hashlib.sha256()
                    remaining = member.size
                    while remaining:
                        data = exact(min(1024 * 1024, remaining))
                        content.update(data)
                        remaining -= len(data)
                    if (
                        expected["content"]
                        and content.hexdigest() != expected["content"]["sha256"]
                    ):
                        raise ContractError("Archive member bytes differ")
                    padding(member.size)
                if exact(1024) != bytes(1024):
                    raise ContractError("Missing archive terminator or extra member")
                while data := read(1024 * 1024):
                    if any(data):
                        raise ContractError("Unexpected archive trailing data")
                if (
                    raw_size != capture["raw_layer"]["size_bytes"]
                    or raw_digest.hexdigest() != capture["raw_layer"]["sha256"]
                ):
                    raise ContractError("Retained raw archive identity mismatch")
        if _identity(os.fstat(descriptor)) != _identity(before) or _identity(
            os.stat(Path(path).name, dir_fd=parent, follow_symlinks=False)
        ) != _identity(before):
            raise InputChanged("Retained archive descriptor/path binding changed")
        _check_parent_path(Path(path).absolute().parent, parent_before)
    except (ContractError, InputChanged):
        raise
    except (
        OSError,
        tarfile.HeaderError,
        UnicodeError,
        ValueError,
        EOFError,
        zlib.error,
    ) as exc:
        raise ContractError("Invalid retained archive bytes") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)
