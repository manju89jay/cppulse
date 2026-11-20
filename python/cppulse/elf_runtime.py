"""Bounded ELF metadata from pinned bytes, without executing a subject or loader.

This finite profile reports literal loader inputs. It does not resolve libraries,
authenticate an executable, or establish a complete runnable dependency closure.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import struct

from cppulse.errors import ContractError
from cppulse.frozen_input import _identity, _open_root


@dataclass(frozen=True)
class ElfRuntimeMetadata:
    """Literal metadata observed in one SHA/size-pinned ELF64LE x86-64 file."""

    sha256: str
    size_bytes: int
    elf_class: int
    machine: int
    elf_type: int
    interpreter: str | None
    needed: tuple[str, ...]
    rpath: str | None
    runpath: str | None


def _inspect(
    descriptor: int, size: int
) -> tuple[int, int, str | None, tuple[str, ...], str | None, str | None]:
    def read(offset: int, count: int) -> bytes:
        if offset < 0 or count < 0 or offset > size or count > size - offset:
            raise ContractError("ELF file range exceeds the pinned byte boundary")
        data = os.pread(descriptor, count, offset)
        if len(data) != count:
            raise ContractError("ELF file changed or has a truncated range")
        return data

    header = struct.unpack("<16sHHIQQQIHHHHHH", read(0, 64))
    ident, kind, machine, version = header[:4]
    phoff, ehsize, phentsize, phnum = header[5], header[8], header[9], header[10]
    if (
        ident[:7] != b"\x7fELF\x02\x01\x01"
        or kind not in (2, 3)
        or machine != 62
        or version != 1
        or ehsize != 64
        or phentsize != 56
        or not 1 <= phnum <= 1024
        or phoff < 64
        or phoff > size
        or phnum * 56 > size - phoff
    ):
        raise ContractError("Unsupported or malformed ELF64LE x86-64 executable header")
    loads, dynamic, interpreters = [], [], []
    for index in range(phnum):
        row = struct.unpack("<IIQQQQQQ", read(phoff + index * 56, 56))
        tag, _, offset, address, _, filesz, memsz, align = row
        if offset > size or filesz > size - offset or memsz > 2**64 - address:
            raise ContractError("ELF segment exceeds file or virtual-address bounds")
        if tag == 1:
            if filesz > memsz or (
                align > 1 and (align & (align - 1) or offset % align != address % align)
            ):
                raise ContractError("Malformed file-backed ELF load segment")
            loads.append((offset, address, filesz, memsz))
        elif tag == 2:
            dynamic.append((offset, address, filesz))
        elif tag == 3:
            interpreters.append((offset, filesz))
    if not loads or len(dynamic) > 1 or len(interpreters) > 1:
        raise ContractError("ELF needs load segments and unambiguous runtime tables")

    def file_offset(address: int, count: int) -> int:
        offsets = {
            offset + address - base
            for offset, base, filesz, _ in loads
            if base <= address and count <= filesz and address - base <= filesz - count
        }
        if len(offsets) != 1:
            raise ContractError(
                "ELF virtual range has no unambiguous file-backed load mapping"
            )
        selected = offsets.pop()
        for offset, base, filesz, memsz in loads:
            start = max(address, base)
            end = min(address + count, base + memsz)
            if start < end and (
                end > base + filesz
                or offset + start - base != selected + start - address
            ):
                raise ContractError(
                    "ELF virtual range has a conflicting partial load mapping"
                )
        return selected

    interpreter = None
    if interpreters:
        offset, count = interpreters[0]
        if not 2 <= count <= 4096:
            raise ContractError("ELF interpreter exceeds the bounded string profile")
        raw = read(offset, count)
        if raw[-1:] != b"\0" or b"\0" in raw[:-1]:
            raise ContractError("ELF interpreter must be one terminated string")
        interpreter = raw[:-1].decode("utf-8", errors="strict")
    if not dynamic:
        return kind, machine, interpreter, (), None, None
    offset, address, count = dynamic[0]
    if count % 16 or not 16 <= count <= 4096 * 16:
        raise ContractError("ELF dynamic table exceeds its finite entry profile")
    if file_offset(address, count) != offset:
        raise ContractError("ELF dynamic file and virtual ranges disagree")
    values, needed = {}, []
    terminated = False
    for index in range(count // 16):
        tag, value = struct.unpack("<qQ", read(offset + index * 16, 16))
        if tag == 0:
            terminated = True
            break
        if tag == 1:
            needed.append(value)
        elif tag in (5, 10, 15, 29):
            if tag in values:
                raise ContractError("ELF dynamic string metadata is ambiguous")
            values[tag] = value
    if not terminated:
        raise ContractError("ELF dynamic table has no bounded DT_NULL terminator")
    if not values and not needed:
        return kind, machine, interpreter, (), None, None
    if 5 not in values or 10 not in values or not 1 <= values[10] <= size:
        raise ContractError("ELF dynamic strings lack a bounded string table")
    string_size = values[10]
    string_offset = file_offset(values[5], string_size)

    def string(index: int) -> str:
        if index >= string_size:
            raise ContractError("ELF dynamic string index lies outside its table")
        raw = read(string_offset + index, min(4096, string_size - index))
        end = raw.find(b"\0")
        if end < 0:
            raise ContractError("ELF dynamic string has no bounded terminator")
        return raw[:end].decode("utf-8", errors="strict")

    libraries = tuple(string(index) for index in needed)
    if any(not name for name in libraries):
        raise ContractError("ELF needed library identity cannot be empty")
    return (
        kind,
        machine,
        interpreter,
        libraries,
        string(values[15]) if 15 in values else None,
        string(values[29]) if 29 in values else None,
    )


def inspect_elf_runtime(
    path: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    max_bytes: int = 268435456,
) -> ElfRuntimeMetadata:
    """Inspect bounded runtime metadata through one pinned nofollow descriptor.

    Hash streaming and metadata reads share the same descriptor. File metadata,
    pathname and parent selection are rechecked before returning, including a
    second streaming hash. No ELF bytes are executed or loaded as code.
    """
    if (
        not isinstance(expected_sha256, str)
        or re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None
        or not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or not isinstance(max_bytes, int)
        or isinstance(max_bytes, bool)
        or not 64 <= expected_size <= max_bytes
    ):
        raise ContractError("ELF inspection requires finite exact SHA/size pins")
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "pread"):
        raise ContractError("ELF inspection requires POSIX nofollow descriptor reads")
    try:
        path = Path(path).absolute()
    except (TypeError, ValueError) as error:
        raise ContractError(
            "ELF inspection requires a selected filesystem pathname"
        ) from error
    if ".." in path.parts or "\x00" in str(path):
        raise ContractError("ELF pathname must not contain parent traversal")
    try:
        parent = _open_root(str(path.parent))
        try:
            selected = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(selected.st_mode) or selected.st_size != expected_size:
                raise ContractError("ELF pathname is not the pinned regular file")
            descriptor = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
            try:
                before = os.fstat(descriptor)
                if _identity(before) != _identity(selected):
                    raise ContractError("ELF pathname changed during selection")

                def digest() -> str:
                    result = hashlib.sha256()
                    for offset in range(0, expected_size, 1024 * 1024):
                        count = min(1024 * 1024, expected_size - offset)
                        block = os.pread(descriptor, count, offset)
                        if len(block) != count:
                            raise ContractError(
                                "ELF bytes changed during streaming hash"
                            )
                        result.update(block)
                    return result.hexdigest()

                if digest() != expected_sha256:
                    raise ContractError("ELF bytes differ from their selected SHA256")
                kind, machine, interpreter, needed, rpath, runpath = _inspect(
                    descriptor, expected_size
                )
                if digest() != expected_sha256 or _identity(
                    os.fstat(descriptor)
                ) != _identity(before):
                    raise ContractError(
                        "ELF bytes or metadata changed during inspection"
                    )
                if _identity(
                    os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                ) != _identity(before):
                    raise ContractError("ELF pathname changed during inspection")
                current_parent = _open_root(str(path.parent))
                try:
                    if _identity(os.fstat(current_parent)) != _identity(
                        os.fstat(parent)
                    ):
                        raise ContractError(
                            "ELF parent pathname changed during inspection"
                        )
                finally:
                    os.close(current_parent)
                return ElfRuntimeMetadata(
                    expected_sha256,
                    expected_size,
                    64,
                    machine,
                    kind,
                    interpreter,
                    needed,
                    rpath,
                    runpath,
                )
            finally:
                os.close(descriptor)
        finally:
            os.close(parent)
    except (OSError, UnicodeError, struct.error, OverflowError) as error:
        raise ContractError(
            "ELF selected bytes are unavailable or malformed"
        ) from error
